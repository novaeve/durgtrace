"""Run in existing server RDKit environment; no API requests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import run_editors as editor


class Relay:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def complete(self, messages, label, cap=None):
        self.calls.append((messages, label, cap))
        return next(self.responses)


class NativeEditorTests(unittest.TestCase):
    def setup_run(self, root):
        values = {'CCO': .2, 'CCN': .8, 'CCCl': .1, 'CCBr': .3,
                  'CCCCCCl': .1, 'CCCCCBr': .3}
        scores = editor.Scores(root, lambda sm: values[sm])
        ledger = editor.SubmissionLedger(root/'answers.jsonl', editor.canonical,
                                        lambda sm: scores.get(sm, 'test_answer'))
        ledger.submit('CCO', 'initial/model')
        return scores, ledger

    def test_chatdrug_native_feedback_and_early_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            scores, ledger = self.setup_run(Path(directory))
            relay = Relay(['- CCCCCCl', '- CCCCCBr'])
            with patch.object(editor.pd, 'read_csv', return_value=pd.DataFrame({'sequence': ['CCN']})):
                trace = editor.chatdrug('qed', 'CCO', ledger, scores, relay)
            self.assertEqual(len(relay.calls), 2)
            self.assertEqual(len(ledger.rows), 3)
            self.assertEqual(ledger.rows[-1]['canonical'], 'CCCCCBr')
            self.assertIn('CCN', trace['record']['CCO']['retrieval_conversation'][0]['retrieval_drug'])
            self.assertTrue(all(cap is None for _, _, cap in relay.calls))

    def test_agentdrug_original_four_generations_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            scores, ledger = self.setup_run(Path(directory))
            relay = Relay(['CCCl']*4)
            with patch.object(editor.pd, 'read_csv', return_value=pd.DataFrame({'SMILES': ['CCN']})):
                trace = editor.agentdrug('qed', 'CCO', ledger, scores, relay)
            self.assertEqual(len(relay.calls), 4)
            self.assertEqual(len(ledger.rows), 5)
            self.assertEqual(ledger.metrics()['duplicates'], 3)
            self.assertEqual(trace['iterations'], 4)
            self.assertTrue(all(cap == 256 for _, _, cap in relay.calls))
            self.assertIn('CCN', relay.calls[1][0][0]['content'])
            self.assertFalse(ledger.exhausted)


if __name__ == '__main__':
    unittest.main()
