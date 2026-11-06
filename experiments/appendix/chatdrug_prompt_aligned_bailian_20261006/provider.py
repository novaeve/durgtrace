"""Use the existing authorized Bailian configuration, preserving generation caps."""
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
import requests
from pilot import RelayError

MODEL = 'deepseek-v4.1-flash'
CONFIG = Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env')


def config():
    values = {}
    for line in CONFIG.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            values[k.strip().lower()] = v.strip().strip('"').strip("'")
    parsed = urlsplit(values['base_url'])
    assert parsed.scheme == 'https' and parsed.hostname.endswith('.aliyuncs.com')
    assert values.get('api_key')
    return values


class Relay:
    def __init__(self, path):
        self.log_path = Path(path)
        self.calls = []
        self.config = config()
        self.session = requests.Session()
        previous = json.loads(self.log_path.read_text()) if self.log_path.exists() else []
        self.replay = [c for c in previous if c.get('output') and
                       c.get('error') in (None, 'OUTPUT_TRUNCATED')]

    def save(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.log_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.calls, ensure_ascii=False, indent=2))
        tmp.replace(self.log_path)

    def complete(self, messages, label, max_tokens=2048):
        if self.replay:
            cached = self.replay.pop(0)
            assert cached['messages'] == messages and cached['label'] == label
            assert cached['requested_model'] == MODEL
            assert cached['request_settings']['max_tokens'] == max_tokens
            self.calls.append(cached)
            self.save()
            if cached.get('stop_reason') == 'max_tokens':
                raise RelayError('OUTPUT_TRUNCATED')
            return cached['output']
        body = {'model': MODEL, 'messages': messages, 'temperature': 0,
                'enable_thinking': False, 'max_tokens': max_tokens, 'stream': False}
        record = {'label': label, 'requested_model': MODEL, 'messages': messages,
                  'provider': 'Alibaba Bailian', 'attempts': [],
                  'request_settings': {'temperature': 0, 'max_tokens': max_tokens, 'enable_thinking': False}}
        self.calls.append(record)
        endpoint = self.config['base_url'].rstrip('/') + '/chat/completions'
        for attempt in range(3):
            start = time.monotonic()
            try:
                response = self.session.post(endpoint, json=body,
                    headers={'Authorization': 'Bearer ' + self.config['api_key'], 'Content-Type': 'application/json'},
                    timeout=(20, 180))
                record['attempts'].append({'attempt': attempt+1, 'status': response.status_code,
                                          'seconds': round(time.monotonic()-start, 3)})
                if response.status_code != 200:
                    status = response.status_code
                    if status in [408, 429, 500, 502, 503, 504, 529] and attempt < 2:
                        response.close()
                        self.save()
                        time.sleep(2**attempt*2)
                        continue
                    try:
                        detail = json.dumps(response.json().get('error', {}), ensure_ascii=False)
                        for v in self.config.values():
                            if v:
                                detail = detail.replace(v, '[redacted]')
                        record['error_detail'] = detail[:500]
                    except ValueError:
                        pass
                    response.close()
                    raise RelayError('HTTP_' + str(status))
                try:
                    data = response.json()
                finally:
                    response.close()
                choices = data.get('choices', [])
                if not choices:
                    raise RelayError('NO_CHOICES')
                choice = choices[0]
                message = choice.get('message', {})
                text = message.get('content') or ''
                stop = choice.get('finish_reason')
                usage = data.get('usage', {})
                record.update(response_model=data.get('model'), output=text,
                    stop_reason='max_tokens' if stop == 'length' else ('refusal' if message.get('refusal') else stop),
                    reasoning_present=bool(message.get('reasoning_content')), raw_usage=usage,
                    usage={'input_tokens': usage.get('prompt_tokens', 0), 'output_tokens': usage.get('completion_tokens', 0),
                           'cache_read_input_tokens': usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)})
                self.save()
                if record['stop_reason'] == 'refusal':
                    return ''
                if stop == 'length':
                    raise RelayError('OUTPUT_TRUNCATED')
                if not text:
                    raise RelayError('NO_TEXT_BLOCK')
                return text
            except requests.RequestException as e:
                detail = str(e)
                for v in self.config.values():
                    if v:
                        detail = detail.replace(v, '[redacted]')
                record['attempts'].append({'attempt': attempt+1, 'error_type': type(e).__name__,
                                          'seconds': round(time.monotonic()-start, 3), 'detail': detail[:500]})
                # Do not retain a failed connection pool between retries.
                self.session.close()
                self.session = requests.Session()
                self.save()
                if attempt < 2:
                    transient_network = 'NameResolutionError' in detail or 'Network is unreachable' in detail
                    time.sleep(20*(attempt+1) if transient_network else 2**attempt*2)
                    continue
                record['error'] = 'TRANSPORT_ERROR'
                self.save()
                raise RelayError('TRANSPORT_ERROR') from None
            except (RelayError, ValueError) as e:
                record['error'] = str(e) if isinstance(e, RelayError) else 'INVALID_JSON'
                self.save()
                raise RelayError(record['error']) from None
        raise RelayError('RETRY_EXHAUSTED')
