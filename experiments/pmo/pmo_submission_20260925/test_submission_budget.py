import ast
import random
import tempfile
import types
import unittest
from pathlib import Path
from submission_budget import SubmissionLedger, SubmissionBudgetExhausted, mt_mol_auc


class BudgetTests(unittest.TestCase):
    def test_matches_mt_mol_source(self):
        source = (Path(__file__).resolve().parent.parent / 'pmo-1k-20260924'
                  / 'source/mt_mol-main/utils/auc.py')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == 'top_auc']
        self.assertEqual(len(nodes), 1)
        ns = {'np': types.SimpleNamespace(mean=lambda xs: sum(xs) / len(xs))}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), ns)
        rng = random.Random(42)
        for _ in range(100):
            positions = sorted(rng.sample(range(1, 1001), rng.randint(1, 30)))
            buffer = {str(i): [rng.random(), position]
                      for i, position in enumerate(positions)}
            for finish in (False, True):
                self.assertAlmostEqual(mt_mol_auc(buffer, finish=finish),
                                       ns['top_auc'](buffer, 10, finish, 1, 1000))

    def test_duplicates_invalid_and_recovery(self):
        calls = []
        def evaluate(sm):
            calls.append(sm)
            return {'A': .2, 'B': .8}[sm]
        canonical = lambda sm: {'a': 'A', 'A': 'A', 'B': 'B'}.get(sm)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'answers.jsonl'
            ledger = SubmissionLedger(path, canonical, evaluate, 4)
            ledger.submit('a', '0')
            ledger.submit('A', '1')
            ledger.submit('bad', '2')
            ledger = SubmissionLedger(path, canonical, evaluate, 4)
            ledger.submit('bad', '2')  # recovery, not another answer
            ledger.submit('B', '3')
            self.assertEqual(calls, ['A', 'B'])
            self.assertEqual(ledger.buffer, {'A': [.2, 1], 'B': [.8, 4]})
            self.assertEqual(ledger.metrics()['submissions'], 4)
            self.assertEqual(ledger.metrics()['duplicates'], 1)
            self.assertEqual(ledger.metrics()['invalid'], 1)
            self.assertTrue(ledger.exhausted)
            with self.assertRaises(SubmissionBudgetExhausted):
                ledger.submit('A', '4')
            with self.assertRaises(ValueError):
                ledger.submit('B', '0')

    def test_1000_identical_answers_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = SubmissionLedger(Path(directory) / 'answers.jsonl',
                                      lambda sm: sm, lambda sm: .8)
            for i in range(1000):
                ledger.submit('A', str(i))
            self.assertEqual(len(ledger.buffer), 1)
            self.assertEqual(ledger.metrics()['duplicates'], 999)
            self.assertTrue(ledger.exhausted)
            self.assertAlmostEqual(ledger.metrics()['auc_top10_mt_mol'], .7996)

    def test_generation_positions_not_compacted(self):
        self.assertAlmostEqual(mt_mol_auc({'A': [.2, 1], 'B': [.8, 4]}, 4,
                                         finish=True), .2125)
        self.assertNotEqual(mt_mol_auc({'A': [.2, 1], 'B': [.8, 4]}, 4,
                                      finish=True),
                            mt_mol_auc({'A': [.2, 1], 'B': [.8, 2]}, 4,
                                       finish=True))

    def test_empty_and_unfinished(self):
        self.assertEqual(mt_mol_auc({}, 1000, finish=True), 0)
        self.assertAlmostEqual(mt_mol_auc({'A': [.8, 1]}, 1000), .0004)


if __name__ == '__main__':
    unittest.main()
