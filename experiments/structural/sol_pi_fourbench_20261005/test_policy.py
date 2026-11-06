"""Regression checks for recovered aborts, truncation safety and provider parity."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import relay
import run


class PolicyTests(unittest.TestCase):
    def test_request_parity(self):
        payload = relay.settings({'model': 'wrong', 'temperature': 1, 'enable_thinking': True,
                                   'reasoning_effort': 'high', 'thinking': True,
                                   'max_tokens': 65536, 'stream': False, 'messages': []})
        self.assertEqual(payload['model'], run.MODEL)
        self.assertEqual(payload['temperature'], 0)
        self.assertIs(payload['enable_thinking'], False)
        self.assertIs(payload['stream'], True)
        self.assertNotIn('max_tokens', payload)
        self.assertNotIn('reasoning_effort', payload)
        self.assertNotIn('thinking', payload)

    def test_final_native_state(self):
        def message(stop, **values):
            return {'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': stop, **values}}
        events = [message('error', errorMessage='This operation was aborted'),
                  {'type': 'compaction_start'}, message('stop', content=[{'type': 'text', 'text': '<answer>CCO</answer>'}])]
        self.assertEqual(run.final_outcome(0, events, False, 0)[:2], ('complete', '<answer>CCO</answer>'))
        self.assertEqual(run.final_outcome(0, events[:1], False, 0)[0], 'error')
        self.assertEqual(run.final_outcome(0, events, True, 0)[0], 'timeout')
        self.assertEqual(run.final_outcome(0, [message('error', errorMessage='Provider output truncated')], False, 1)[0], 'provider_limit')

    def test_final_answer_parser(self):
        self.assertEqual(run.parse('<answer>N<-[Cu+2]</answer>'), 'N<-[Cu+2]')
        self.assertIsNone(run.parse('<answer>CCO</answer><answer>CC</answer>'))
        self.assertIsNone(run.parse('<answer>CCO'))
        self.assertIsNone(run.parse('<answer><bad>CCO</bad></answer>'))

    def test_truncated_tool_never_forwarded(self):
        chunks = [dict(id='fake', model=run.MODEL, choices=[{'index': 0, 'delta': {'tool_calls': [
            {'index': 0, 'id': 'fake-call', 'function': {'name': 'bash', 'arguments': '{"command":"'}}]}, 'finish_reason': None}]),
            dict(model=run.MODEL, choices=[{'index': 0, 'delta': {}, 'finish_reason': 'length'}], usage={'completion_tokens': 8192})]
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_lines(self, **kwargs):
                yield from [b'data: ' + json.dumps(c).encode() for c in chunks]
                yield b'data: [DONE]'
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(relay, 'load_credentials', return_value={'base_url': 'http://test', 'api_key': 'test'}):
                boundary = relay.Relay(directory)
            with patch.object(relay.requests, 'post', return_value=Response()):
                with self.assertRaisesRegex(RuntimeError, 'no truncated tool call executed'):
                    boundary.complete({'messages': [], 'stream': True})
            self.assertEqual(boundary.truncations, 1)
            record = json.loads(next((Path(directory) / 'api').glob('*.json')).read_text())
            self.assertEqual(record['response']['choices'][0]['finish_reason'], 'length')
            self.assertIn('truncated', record['error'])


if __name__ == '__main__':
    unittest.main()
