import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import run_liddia_type4 as runner
from liddia_flow import validate_inputs, CodeExecutionError, parse_goal


class ReplayAgent:
    def __init__(self, responses):
        self.responses=iter(responses);self.calls=[];self.tokens=0
    def ask(self,prompt,label,system=None):
        self.calls.append({'label':label,'prompt':prompt})
        return next(self.responses)


class FlowTests(unittest.TestCase):
    def test_missing_reference_rejected_before_codegen(self):
        with self.assertRaisesRegex(ValueError,'MOL007'):
            validate_inputs('CODE',['MOL008'],'Compare MOL008 with MOL007',{},'POCKET006')

    def test_codegen_repairs_using_actual_errors_in_real_sandbox(self):
        agent=ReplayAgent([
            '```python\nimport os\ndef _function(data):\n    return data["MOL008"]\n```',
            '```python\ndef _function(data):\n    return data["MOL007"]\n```',
            '```python\ndef _function(data):\n    return data["MOL008"]\n```'])
        with tempfile.TemporaryDirectory() as folder:
            result,meta=runner.code_action(agent,{'MOL008':pd.DataFrame({'SMILES':['CC'],'SAScore':[1.0],'Similarity':[1.0]})},'Select MOL008',Path(folder))
        self.assertEqual(list(result.SMILES),['CC'])
        self.assertEqual(len(meta['errors']),2)
        self.assertIn('Unsupported CODE imports',agent.calls[1]['prompt'])
        self.assertIn("KeyError: 'MOL007'",agent.calls[2]['prompt'])
        self.assertIn('def _function(data: dict[str, pd.DataFrame])',agent.calls[0]['prompt'])
        self.assertNotIn('def _function(Dict[str, pd.DataFrame])',agent.calls[0]['prompt'])

    def test_empty_selection_valid(self):
        agent=ReplayAgent(['```python\ndef _function(data):\n    return data["MOL008"].iloc[:0]\n```'])
        with tempfile.TemporaryDirectory() as folder:
            df,_=runner.code_action(agent,{'MOL008':pd.DataFrame({'SMILES':['CC']})},'Select MOL008',Path(folder))
        self.assertTrue(df.empty)
        self.assertIn('SMILES',df)

    def test_three_code_failures_are_recoverable(self):
        agent=ReplayAgent(['```python\nraise ValueError("intentional failure")\n```']*3)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(CodeExecutionError):
            runner.code_action(agent,{'MOL007':pd.DataFrame({'SMILES':['CC']})},'Select MOL007',Path(folder))
        self.assertEqual(len(agent.calls),3)

    def test_controller_continues_after_code_and_input_errors(self):
        sequence=[
            'Action: CODE002\nInput: ["MOL007"]\nDesc: Select MOL007',
            'Action: ADMET003\nInput: ["MOL999",0]',
            'Action: CODE002\nInput: ["MOL007"]\nDesc: Select MOL007',
            'Action: SUBMIT005\nInput: ["MOL007",0]']
        agent=ReplayAgent(sequence)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'benchmark').symlink_to(runner.ROOT/'benchmark',target_is_directory=True)
            with patch.object(runner,'ROOT',root),patch.object(runner,'Agent',return_value=agent),patch.object(runner,'code_action',side_effect=[CodeExecutionError('three failures'),(pd.DataFrame(columns=['SMILES']),{})]),patch.object(sys,'argv',['runner','--run','test']):
                runner.main()
            out=root/'runs/test/smdd_004_ABL1_1'
            result=json.loads((out/'agent_result.json').read_text())
            events=json.loads((out/'trajectory.json').read_text())
            self.assertEqual(result['status'],'submitted')
            self.assertEqual(result['budget_used'],{'admet':0,'boltz':0})
            self.assertEqual(len(events),4)
            self.assertIn('three failures',agent.calls[1]['prompt'])
            self.assertIn('Unknown molecule-set ID',agent.calls[2]['prompt'])
            self.assertEqual(events[2]['output'],'EMPTY SET')

    def test_goal_missing_format_is_controlled_error(self):
        with self.assertRaises(ValueError):parse_goal('I think yes')
        self.assertEqual(parse_goal('Reason: scores absent\nAnswer: NO'),('NO','scores absent'))

    def test_controller_continues_after_boltz_failure(self):
        from runtime_safety import ToolExecutionError
        agent=ReplayAgent(['Action: BOLTZ004\nInput: ["MOL007",0]',
                           'Action: SUBMIT005\nInput: ["MOL007",0]'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'benchmark').symlink_to(runner.ROOT/'benchmark',target_is_directory=True)
            with patch.object(runner,'ROOT',root),patch.object(runner,'Agent',return_value=agent),patch.object(runner,'boltz',side_effect=ToolExecutionError('synthetic OOM')),patch.object(sys,'argv',['runner','--run','test']):
                runner.main()
            result=json.loads((root/'runs/test/smdd_004_ABL1_1/agent_result.json').read_text())
            self.assertEqual(result['status'],'submitted')
            self.assertEqual(result['budget_used']['boltz'],1)
            self.assertIn('synthetic OOM',agent.calls[1]['prompt'])


if __name__=='__main__':unittest.main()
