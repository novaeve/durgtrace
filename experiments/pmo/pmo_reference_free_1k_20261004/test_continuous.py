import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import continuous as c


class FakeRelay:
    def __init__(self, out):
        self.out = out
        self.long_truncations = set()
    def complete(self, messages, label, cap=None):
        # Every episode succeeds with the same perfect-scoring answer.
        return 'C'
    def usage(self):
        calls = len(list((self.out/'episodes').glob('*/model_outputs.json')))
        return {'llm_calls': calls}


def fake_native(task, parent, outputs, scores, relay):
    scores.get(parent, 'parent_feedback')
    text = relay.complete([], 'candidate/1')
    outputs.submit(text, 'candidate/1')
    scores.get(text, 'candidate_feedback')
    return {'hit': True}


class ContinuousTests(unittest.TestCase):
    def invoke(self, root, quantum, budget=1000, native=fake_native):
        with patch.object(c, 'ROOT', root), patch.object(c, 'verify', return_value={'frozen_inputs': {}}), \
             patch.object(c, 'editor', return_value=native), patch.object(c.n, 'Relay', FakeRelay), \
             patch.object(c.n, 'make_oracle', return_value=lambda sm: 1.0):
            return c.job('chatdrug', 'qed', 'pilot', budget, quantum)

    def test_success_and_duplicates_still_reach_real_1000(self):
        with tempfile.TemporaryDirectory(dir=c.ROOT) as temporary:
            root = Path(temporary)
            result = self.invoke(root, quantum=1000)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['oracle_submissions'], 1000)
            self.assertFalse(result['auc_is_tail_filled'])
            self.assertGreater(result['episodes'], 1)
            self.assertGreater(result['duplicates'], 900)
            out = root/'pilot/chatdrug/qed/0'
            self.assertEqual(len((out/'oracle_queries.jsonl').read_text().splitlines()), 1000)

    def test_yield_is_not_terminal_and_resumes_without_recharging_initial(self):
        with tempfile.TemporaryDirectory(dir=c.ROOT) as temporary:
            root = Path(temporary)
            first = self.invoke(root, quantum=2, budget=20)
            out = root/'pilot/chatdrug/qed/0'
            self.assertEqual(first['status'], 'yielded')
            self.assertFalse((out/'result.json').exists())
            rows = [json.loads(s) for s in (out/'oracle_queries.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 5)
            while True:
                result = self.invoke(root, quantum=2, budget=20)
                if result['status'] != 'yielded':
                    break
            rows = [json.loads(s) for s in (out/'oracle_queries.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 20)
            self.assertEqual(sum(r['event_id'].endswith('/initial_model_answer') for r in rows), 1)
            self.assertEqual(result['status'], 'complete')

    def test_interrupted_episode_replays_counted_queries_once(self):
        with tempfile.TemporaryDirectory(dir=c.ROOT) as temporary:
            root = Path(temporary)
            def interrupted(task, parent, outputs, scores, relay):
                scores.get(parent, 'parent_feedback')
                raise RuntimeError('Simulated interruption before model call')
            with self.assertRaises(RuntimeError):
                self.invoke(root, quantum=10, budget=12, native=interrupted)
            result = self.invoke(root, quantum=10, budget=12)
            out = root/'pilot/chatdrug/qed/0'
            rows = [json.loads(s) for s in (out/'oracle_queries.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 12)
            self.assertEqual([r['index'] for r in rows], list(range(1, 13)))
            self.assertEqual(result['status'], 'complete')

    def test_reference_and_fingerprint_caches_preserve_native_behavior(self):
        with tempfile.TemporaryDirectory(dir=c.ROOT) as temporary:
            out = Path(temporary)
            oracle = c.Oracle(out, lambda sm: 0.5, 'agentdrug', 'qed', 10)
            lib = c.base.library('agentdrug')[1]
            self.assertEqual(len(oracle.reference_db), 10000)
            self.assertEqual(list(oracle.reference_db['SMILES']), lib)
            self.assertEqual(oracle.cursor, 0)
            cached = c.CachedMorgan()
            for mol in oracle.reference_db['mol'].iloc[:5]:
                self.assertEqual(cached.GetMorganFingerprint(mol, 2), c.n.AllChem.GetMorganFingerprint(mol, 2))
            # Compile both unchanged native editing workflows against the prepared DB.
            self.assertTrue(callable(c.editor('chatdrug', cached)))
            self.assertTrue(callable(c.editor('agentdrug', cached)))

    def test_chat_native_retrieval_accepts_author_newline_cleanup(self):
        with tempfile.TemporaryDirectory(dir=c.ROOT) as temporary:
            out = Path(temporary)
            parent = json.loads((c.PREVIOUS/'initial_answers.json').read_text())['qed']['raw']
            parent_sm = c.n.canonical(parent)
            def evaluate(sm):
                return 0.5 if sm == parent_sm else (0.1 if sm == 'CCCOCCC' else 0.9)
            oracle = c.Oracle(out, evaluate, 'chatdrug', 'qed', 20)
            first_raw = oracle.reference_db.iloc[0]['sequence']
            oracle.get(first_raw.replace('\n', ''), 'retrieval_feedback')
            self.assertEqual(oracle.cursor, 0)
            oracle.get(parent, 'initial_model_answer')
            class Relay:
                def __init__(self): self.calls = 0
                def complete(self, *args, **kwargs):
                    self.calls += 1
                    return '- CCCOCCC' if self.calls == 1 else '- CCNCCCC'
            relay = Relay()
            outputs = c.Outputs(out, oracle)
            trace = c.editor('chatdrug', c.CachedMorgan())('qed', parent, outputs, oracle, relay)
            self.assertGreater(len(oracle.free_ids), 1)
            self.assertEqual(relay.calls, 2)
            self.assertIn('Retrieval Result:', trace['log'])
            self.assertNotIn('Invalid drug. Failed to evaluate.', trace['log'])


if __name__ == '__main__':
    unittest.main()
