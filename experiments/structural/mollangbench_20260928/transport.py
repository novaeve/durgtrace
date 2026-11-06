import ast, hashlib, json, pathlib, time
import requests
MODEL="deepseek-v4.1-flash"
def dump(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def functions(path, names, ns):
    tree = ast.parse(pathlib.Path(path).read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert set((n.name for n in nodes)) == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns

class APIError(Exception):
    pass

class LongTruncation(BaseException):
    """Provider-default output truncated; do not parse or score the partial text."""

def long_truncation(record):
    return record.get('finish_reason') == 'length' and record.get('request', {}).get('max_tokens') is None

class Relay:

    def __init__(self, out):
        self.out = out
        self.calls = 0
        self.session = requests.Session()
        self.long_truncations = set()
        for path in (out / 'api').glob('*.json'):
            if long_truncation(json.loads(path.read_text())):
                self.long_truncations.add(path.stem)
        self.config = {}
        for line in pathlib.Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and (not line.lstrip().startswith('#')):
                k, v = line.split('=', 1)
                self.config[k.strip().lower()] = v.strip().strip('"').strip("'")

    def complete(self, messages, label, cap=None):
        body = {'model': MODEL, 'messages': messages, 'temperature': 0, 'enable_thinking': False, 'stream': False}
        if cap is not None:
            body['max_tokens'] = cap
        key = hashlib.sha256(json.dumps({'body': body, 'label': label}, sort_keys=True).encode()).hexdigest()
        target = self.out / 'api' / f'{key}.json'
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            previous = json.loads(target.read_text())
            if 'output' in previous:
                if long_truncation(previous):
                    self.long_truncations.add(key)
                    raise LongTruncation()
                return previous['output']
        record = {'label': label, 'request': body, 'attempts': [], 'started': time.time()}
        for attempt in range(4):
            start = time.monotonic()
            try:
                response = self.session.post(self.config['base_url'].rstrip('/') + '/chat/completions', json=body, headers={'Authorization': 'Bearer ' + self.config['api_key']}, timeout=(20, 180))
                record['attempts'].append({'status': response.status_code, 'seconds': time.monotonic() - start})
                if response.status_code != 200:
                    status = response.status_code
                    response.close()
                    dump(target, record)
                    if status in [408, 429, 500, 502, 503, 504] and attempt < 3:
                        time.sleep(2 ** attempt * 2)
                        continue
                    raise APIError('HTTP_' + str(status))
                data = response.json()
                response.close()
                choice = data.get('choices', [{}])[0]
                record.update(output=choice.get('message', {}).get('content') or '', usage=data.get('usage', {}), response_model=data.get('model'), finish_reason=choice.get('finish_reason'), ended=time.time())
                dump(target, record)
                self.calls += 1
                if long_truncation(record):
                    self.long_truncations.add(key)
                    raise LongTruncation()
                return record['output']
            except requests.RequestException as e:
                record['attempts'].append({'error_type': type(e).__name__, 'seconds': time.monotonic() - start})
                dump(target, record)
                if attempt < 3:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise APIError('TRANSPORT_ERROR') from None

    def usage(self):
        records = [json.loads(p.read_text()) for p in (self.out / 'api').glob('*.json')]
        return {'llm_calls': sum(('output' in r for r in records)), 'http_attempts': sum((len(r['attempts']) for r in records)), 'prompt_tokens': sum((r.get('usage', {}).get('prompt_tokens', 0) for r in records)), 'completion_tokens': sum((r.get('usage', {}).get('completion_tokens', 0) for r in records)), 'truncated': sum((r.get('finish_reason') == 'length' for r in records))}
