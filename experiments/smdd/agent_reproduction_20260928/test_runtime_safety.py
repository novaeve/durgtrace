from pathlib import Path
from unittest.mock import patch
import ast
import json
import subprocess
import tempfile
import unittest
import numpy as np
import pandas as pd
from runtime_safety import atomic_json,read_json_record,require_gpu,select_gpu,ToolExecutionError,ResourceUnavailable
from smdd_liddia_tools import BudgetGate,GraphGATool
import smdd_backends as backends


class RuntimeTests(unittest.TestCase):
    def test_pocket_ragged_scores_preserve_original_formula(self):
        text=(Path('/data2/chenfuxin/agent_reproduction_20260928/Pocket2Mol/sample.py')).read_text()
        tree=ast.parse(text)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='logp_to_rank_prob')
        scope={'np':np};exec(compile(ast.Module(body=[node],type_ignores=[]),'original_rank','exec'),scope)
        scores=[np.array([-1.,-2.]),np.array([-1.,-2.,-3.])]
        with self.assertRaises(ValueError):np.array(scores)
        weights=[.5,.25]
        actual=scope['logp_to_rank_prob'](scores,weights)
        expected=(np.exp([-3.,-6.])+1)*weights
        np.testing.assert_allclose(actual,expected/expected.sum())
        regular=np.array([[-1.,-2.],[-3.,-4.]])
        np.testing.assert_array_equal(scope['logp_to_rank_prob'](regular,weights),scope['logp_to_rank_prob'](list(regular),weights))

    def test_atomic_write_preserves_previous_on_disk_error(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json';atomic_json(p,{'old':1})
            with patch('runtime_safety.json.dump',side_effect=OSError(28,'disk full')),self.assertRaises(OSError):atomic_json(p,{'new':2})
            self.assertEqual(read_json_record(p),{'old':1})
            p.write_text('');self.assertEqual(read_json_record(p)['status'],'corrupt_record')

    def test_gpu_insufficient_stops_before_inference(self):
        with patch('runtime_safety.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout='8000\n')):
            with self.assertRaises(ResourceUnavailable):require_gpu(1)

    def test_gpu_selection_uses_free_card_and_refuses_busy_cards(self):
        with patch('runtime_safety.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout='0, 32000\n1, 8000\n')):
            self.assertEqual(select_gpu(1),0)
        with patch('runtime_safety.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout='0, 20000\n1, 8000\n')):
            with self.assertRaises(ResourceUnavailable):select_gpu(1)

    def test_failed_backend_is_charged_once_no_free_retry(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(s):raise ToolExecutionError('synthetic OOM')
            gate=BudgetGate(Path(d)/'budget.jsonl',{'boltz':fail})
            with self.assertRaises(ToolExecutionError):gate.predict('boltz','CC')
            self.assertEqual(gate.used['boltz'],1)
            events=[json.loads(x) for x in gate.journal.read_text().splitlines()]
            self.assertEqual([x['event'] for x in events],['reserved','error'])

    def test_graphga_retains_scores_before_backend_error(self):
        class Optimizer:
            def __init__(self,**kwargs):self.oracle=type('Oracle',(),{})()
            def optimize(self,oracle,**kwargs):oracle('CC');oracle('CCC')
        def scorer(s):
            if s=='CCC':raise ToolExecutionError('synthetic OOM')
            return .5
        with tempfile.TemporaryDirectory() as d,patch('molopt.graph_ga.GraphGA',Optimizer):
            df,meta=GraphGATool({'BindingAffinity':scorer})(pd.DataFrame({'SMILES':['CC']}),'BindingAffinity',100,d)
            self.assertEqual(list(df.SMILES),['CC'])
            self.assertTrue(meta['stop'].startswith('tool_error:'))

    def test_boltz_subprocess_error_becomes_tool_error(self):
        with tempfile.TemporaryDirectory() as d,patch.object(backends,'ROOT',Path(d)),patch.object(backends,'require_disk'),patch.object(backends,'require_gpu'),patch.object(backends,'wait_for_gpu',return_value=0),patch.object(backends.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['boltz'])) as run:
            with self.assertRaises(ToolExecutionError):backends.boltz_payload({},Path(d)/'jobs')
            cmd=run.call_args.args[0]
            self.assertEqual(cmd[cmd.index('--max_parallel_samples')+1],'1')
            self.assertEqual(cmd[cmd.index('--diffusion_samples')+1],'10')
            self.assertEqual(run.call_count,1)


if __name__=='__main__':unittest.main()
