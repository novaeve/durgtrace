"""Host-only DeepSeek relay; actual provider settings match the frozen baseline."""
from pathlib import Path
import http.server
import json
import threading
import time
import requests

MODEL = 'deepseek-v4.1-flash'
CREDENTIAL_SOURCE = Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env')


def load_credentials():
    values = {}
    for line in CREDENTIAL_SOURCE.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.strip().removeprefix('export ').split('=', 1)
            values[key.strip().lower()] = value.strip().strip('"').strip("'")
    assert values.get('api_key') and values.get('base_url')
    return values


def settings(body):
    payload = dict(body)
    payload.update(model=MODEL, temperature=0, enable_thinking=False, stream=True)
    # All 113278 inspected baseline requests omit max_tokens and thinking effort.
    for key in ('reasoning_effort', 'reasoning', 'thinking', 'max_tokens',
                'max_completion_tokens', 'store'):
        payload.pop(key, None)
    return payload


def assemble(chunks):
    text, tools, finish, usage, model = [], {}, None, {}, None
    for chunk in chunks:
        model = chunk.get('model', model)
        if chunk.get('usage'):
            usage = chunk['usage']
        for choice in chunk.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            delta = choice.get('delta') or {}
            if delta.get('content'):
                text.append(delta['content'])
            if choice.get('finish_reason'):
                finish = choice['finish_reason']
            for part in delta.get('tool_calls') or []:
                current = tools.setdefault(part['index'], {'id': '', 'type': 'function',
                                            'function': {'name': '', 'arguments': ''}})
                if part.get('id'):
                    current['id'] = part['id']
                for field in ('name', 'arguments'):
                    current['function'][field] += part.get('function', {}).get(field, '')
    message = {'role': 'assistant', 'content': ''.join(text) or None}
    if tools:
        message['tool_calls'] = [tools[i] for i in sorted(tools)]
    first = next((c for c in chunks if c.get('id')), {})
    return {'id': first.get('id', 'provider-response'), 'object': 'chat.completion',
            'created': first.get('created', int(time.time())), 'model': model,
            'choices': [{'index': 0, 'message': message, 'finish_reason': finish}], 'usage': usage}


def guard(name, inputs):
    if name in ('write', 'edit'):
        path = str(inputs.get('path', '')).removeprefix('/workspace/').removeprefix('./')
        if path.startswith('.agent/') or path in ('.pi/session.jsonl', '.pi/loaded-runtime.json'):
            return 'Benchmark runtime configuration and session evidence are managed externally.'
    return None


class Relay:
    def __init__(self, out):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.credentials = load_credentials()
        self.lock = threading.Lock()
        self.calls = 0
        self.truncations = 0

    def record(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        temp.replace(path)

    def complete(self, body):
        with self.lock:
            self.calls += 1
            number = self.calls
        payload = settings(body)
        record = {'request': payload, 'started': time.time(), 'settings': {
            'model': MODEL, 'temperature': 0, 'enable_thinking': False,
            'reasoning_effort': None, 'max_tokens': None, 'stream': True,
            'credential_source': str(CREDENTIAL_SOURCE)}}
        path = self.out / 'api' / f'{number:06d}.json'
        self.record(path, record)
        try:
            chunks, lines = [], []
            with requests.post(self.credentials['base_url'].rstrip('/') + '/chat/completions',
                               json=payload, headers={'Authorization': 'Bearer ' + self.credentials['api_key']},
                               stream=True, timeout=(30, 300)) as response:
                record['http_status'] = response.status_code
                if response.status_code != 200:
                    record['upstream_error'] = response.text.replace(self.credentials['api_key'], '[REDACTED]')[:1500]
                    record['error'] = 'upstream_http_' + str(response.status_code)
                    raise RuntimeError(record['error'])
                for line in response.iter_lines(chunk_size=4096):
                    if not line:
                        continue
                    lines.append(line)
                    if line.startswith(b'data: ') and line != b'data: [DONE]':
                        chunk = json.loads(line[6:])
                        if chunk.get('error'):
                            record['upstream_error'] = json.dumps(chunk['error']).replace(self.credentials['api_key'], '[REDACTED]')[:1500]
                            raise RuntimeError('upstream_stream_error')
                        if chunk.get('model') and chunk['model'] != MODEL:
                            raise RuntimeError('provider_model_mismatch')
                        chunks.append(chunk)
            result = assemble(chunks)
            record['response'] = result
            if result['model'] != MODEL or result['choices'][0]['finish_reason'] is None:
                raise RuntimeError('incomplete_provider_stream')
            # Buffer the complete stream before forwarding; never execute partial tool arguments.
            if result['choices'][0]['finish_reason'] == 'length':
                with self.lock:
                    self.truncations += 1
                raise RuntimeError('Provider output truncated; no truncated tool call executed')
            return result, lines
        except Exception as exc:
            record['error'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            raise
        finally:
            record['ended'] = time.time()
            self.record(path, record)

    def service(self):
        state = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, obj, status=200):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                    if self.path == '/guard':
                        self.send({'reason': guard(body['name'], body.get('input') or {})})
                        return
                    if self.path != '/v1/chat/completions':
                        self.send({'error': {'message': 'Unknown endpoint'}}, 404)
                        return
                    result, lines = state.complete(body)
                    if not body.get('stream'):
                        self.send(result)
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    for line in lines:
                        self.wfile.write(line + b'\n\n')
                    if not any(line == b'data: [DONE]' for line in lines):
                        self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                    self.close_connection = True
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                    try:
                        self.send({'error': {'message': error}}, 400)
                    except OSError:
                        pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
