"""Validate original case/evaluation preservation and launch the baseline lanes."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, '/data2/chenfuxin/chatdrug_generalization_20260920')
from provider import Relay


class FakeResponse:
    status_code = 200

    def json(self):
        return {'model': 'deepseek-v4.1-flash',
                'choices': [{'message': {'content': 'CCO'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 3}}

    def close(self):
        pass


class FakeSession:
    def __init__(self):
        self.bodies = []

    def post(self, endpoint, headers, json, timeout):
        self.bodies.append(copy.deepcopy(json))
        return FakeResponse()


def main():
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        for cap in [256, 2048]:
            path = Path(directory)/('calls_'+str(cap)+'.json')
            messages = [{'role': 'user', 'content': 'Offline test; do not send this to a model.'}]
            original = copy.deepcopy(messages)
            relay = Relay(path)
            relay.session = FakeSession()
            assert relay.complete(messages, 'offline', max_tokens=cap) == 'CCO'
            assert relay.session.bodies[0]['max_tokens'] == cap
            assert relay.session.bodies[0]['temperature'] == 0
            assert relay.session.bodies[0]['enable_thinking'] is False
            messages.append({'role': 'assistant', 'content': 'Later mutation'})
            assert json.loads(path.read_text())[0]['messages'] == original
            replay = Relay(path)
            def forbidden(*args, **kwargs):
                raise AssertionError('Replay must not request the API')
            replay.session.post = forbidden
            assert replay.complete(original, 'offline', max_tokens=cap) == 'CCO'
    subprocess.run([sys.executable, str(ROOT/'run.py'), 'prepare'], check=True)
    p = ROOT/'validation.json'
    validation = json.loads(p.read_text())
    validation['transport_offline_tests'] = {'no_model_calls': True, 'caps_verified': [256, 2048],
                                             'immutable_request_log': True, 'cached_replay': True}
    p.write_text(json.dumps(validation, ensure_ascii=False, indent=2))
    manifest_path = ROOT/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['network_recovery'] = 'Wait for temporary network recovery, preserve failed attempts, reuse completed replies, and resume only incomplete cases; scoring and prompts unchanged.'
    manifest['launcher_sha256'] = hashlib.sha256((ROOT/'launch.py').read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    subprocess.run([sys.executable, str(ROOT/'launch.py'), 'launch'], check=True)
    print('ORIGINAL_BASELINE_LAUNCHED', flush=True)


if __name__ == '__main__':
    main()
