import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import run_oracle_editors as runner


class OracleProtocolTests(unittest.TestCase):
    def test_repeated_queries_consume_budget_and_replay_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            oracle = runner.UnifiedOracle(path, lambda sm: .4, budget=3)
            for source in ['initial', 'reference', 'feedback']:
                oracle.get('CCO', source)
            self.assertEqual(oracle.physical_this_process, 1)
            self.assertEqual(len(oracle.ledger.rows), 3)
            with self.assertRaises(runner.OracleBudgetExhausted):
                oracle.get('CCN', 'final')
            replay = runner.UnifiedOracle(path, lambda sm: self.fail('Replay evaluated again'), budget=3)
            for source in ['initial', 'reference', 'feedback']:
                replay.get('CCO', source)
            self.assertEqual(len(replay.ledger.rows), 3)

    def test_native_reference_preparation_hits_shared_cap_before_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            oracle = runner.UnifiedOracle(path, lambda sm: .4, budget=3)
            oracle.get('CCO', 'initial_model_answer')
            outputs = runner.Generations(path, oracle)
            class NoModel:
                def complete(self, *args, **kwargs):
                    raise AssertionError('Model invoked after reference budget exhausted')
            with patch.object(runner.native.pd, 'read_csv',
                              return_value=pd.DataFrame({'SMILES': ['CCN']*4})):
                with self.assertRaises(runner.OracleBudgetExhausted):
                    runner.native.agentdrug('qed', 'CCO', outputs, oracle, NoModel())
            self.assertEqual(len(oracle.ledger.rows), 3)
            self.assertEqual(len(outputs.rows), 0)
            self.assertEqual(oracle.ledger.metrics()['duplicates'], 1)

    def test_final_reporting_does_not_double_charge_existing_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            oracle = runner.UnifiedOracle(path, lambda sm: .4)
            outputs = runner.Generations(path, oracle)
            outputs.submit('CCO', 'output/1')
            oracle.get('CCO', 'feedback')
            runner.finish_last_output(outputs, oracle)
            self.assertEqual(len(oracle.ledger.rows), 1)
            outputs.submit('CCN', 'output/2')
            runner.finish_last_output(outputs, oracle)
            self.assertEqual(len(oracle.ledger.rows), 2)

    def test_chatdrug_cannot_continue_after_feedback_uses_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            oracle = runner.UnifiedOracle(path, lambda sm: .9 if sm == 'CCO' else .1, budget=3)
            oracle.get('CCO', 'initial_model_answer')
            outputs = runner.Generations(path, oracle)
            class OneResponse:
                calls = 0
                def complete(self, *args, **kwargs):
                    self.calls += 1
                    if self.calls > 1:
                        raise AssertionError('Extra model call after oracle cap')
                    return '- CCCCCCl'
            relay = OneResponse()
            with patch.object(runner.native.pd, 'read_csv',
                              return_value=pd.DataFrame({'sequence': ['CCN']})):
                runner.native.chatdrug('qed', 'CCO', outputs, oracle, relay)
            runner.finish_last_output(outputs, oracle)
            self.assertEqual(len(oracle.ledger.rows), 3)
            self.assertEqual(relay.calls, 1)


if __name__ == '__main__':
    unittest.main()
