import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import requests
import run


class PolicyTests(unittest.TestCase):
    def test_submission_is_authoritative(self):
        aborted = [{'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': 'error',
                                                      'errorMessage': 'This operation was aborted'}}]
        self.assertEqual(run.classify(True, 0, aborted, False, None, 0), 'complete')
        recovered = aborted + [{'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': 'stop'}}]
        self.assertEqual(run.classify(False, 0, recovered, False, None, 0), 'complete')
        self.assertEqual(run.classify(False, 0, aborted, False, None, 0), 'infrastructure_error')
        self.assertEqual(run.classify(False, 0, aborted, False, 'budget_exhausted', 0), 'budget_exhausted')

    def test_file_fusion_and_science_boundary(self):
        self.assertIsNotNone(run.guard('write', {'path': '.agent/sol-pi.json'}))
        self.assertIsNotNone(run.guard('read', {'path': '/data2/chenfuxin/hidden'}))
        self.assertIsNotNone(run.guard('bash', {'command': 'python calculate.py'}))
        self.assertIsNotNone(run.guard('write', {'path': 'x.txt', 'then_run': {'command': 'curl http://example.com'}}))
        self.assertIsNone(run.guard('write', {'path': 'x.txt', 'then_run': {'command': 'wc -c x.txt'}}))

    def test_shared_model_budget_and_submit_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(run, 'create_api', return_value=SimpleNamespace(calls=100, total_tokens=0)):
                boundary = run.Boundary('type2', folder, folder)
            server = boundary.service()
            try:
                response = requests.post(f'http://127.0.0.1:{server.server_port}/v1/chat/completions',
                                         json={'messages': []}, timeout=5)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(boundary.api.calls, 100)
                self.assertEqual(boundary.error, 'budget_exhausted')
                boundary.api.calls = 0
                boundary.submitted = True
                response = requests.post(f'http://127.0.0.1:{server.server_port}/v1/chat/completions',
                                         json={'messages': []}, timeout=5)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(boundary.api.calls, 0)
                self.assertEqual(boundary.requests_after_submit, 1)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
