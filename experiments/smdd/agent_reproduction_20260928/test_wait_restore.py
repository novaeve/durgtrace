from pathlib import Path
import json
import random
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
import run_liddia_type4 as runner
from restore_liddia_state import restore
from runtime_safety import wait_for_gpu,ResourceUnavailable
from smdd_liddia_tools import BudgetGate
from type4_resume_plan import build_plan


class RestoreTests(unittest.TestCase):
    def test_wait_until_gpu_recovers(self):
        with tempfile.TemporaryDirectory() as d,patch('runtime_safety.select_gpu',side_effect=[ResourceUnavailable('busy'),0]),patch('runtime_safety.time.sleep') as sleep:
            path=Path(d)/'status.json'
            self.assertEqual(wait_for_gpu(1,path),0)
            self.assertEqual(sleep.call_count,1)
            self.assertEqual(json.loads(path.read_text())['state'],'ready')

    def test_real_interrupted_state_restores_without_budget_reset(self):
        original=runner.ROOT/'runs/full_type4_runtimefix2/smdd_004_ABL1_11'
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            for name in ('agent_result.json','budget.jsonl','llm_calls.json','molecule_sets.json','trajectory.json'):
                shutil.copy2(original/name,out/name)
            (out/'resume_origin.json').write_text(json.dumps({'source':str(original)}))
            gate=BudgetGate(out/'budget.jsonl',{},resume=True)
            self.assertEqual(gate.used,{'admet':15,'boltz':2})
            agent=SimpleNamespace(calls=[],tokens=0)
            memory=runner.Memory();actions={}
            for name in ('GENERATE','OPTIMIZE','CODE','ADMET','BOLTZ','SUBMIT'):
                actions[memory.add_action(name,desc='test',cost='1',return_id=True)]=name
            memory.add_pocket('protein.pdb',desc='test')
            memory.add_mol(pd.DataFrame({'SMILES':['CC']}),action='test',metrics={})
            known={};events=[]
            step,feedback=restore(out,agent,memory,known,events,gate,SimpleNamespace(rng=random.Random(42)),SimpleNamespace(rng=random.Random(42)),actions)
            previous=json.loads((original/'agent_result.json').read_text())
            self.assertEqual(len(agent.calls),previous['llm_calls'])
            self.assertEqual(agent.tokens,previous['tokens'])
            self.assertEqual(step,10)
            self.assertIn('MOL010',memory.stream)
            self.assertTrue(known)
            self.assertEqual((out/'budget.jsonl').read_bytes(),(original/'budget.jsonl').read_bytes())
            print('RESTORED',len(agent.calls),'LLM calls;',gate.used,'next_step',step)

    def test_real_multigeneration_plan_keeps_all_nineteen_results(self):
        tasks=sorted(p.name for p in (runner.ROOT/'benchmark/tasks').glob('smdd_004*') if p.is_dir())
        plan=build_plan(tasks,runner.ROOT/'runs/full_type4_runtimefix2')
        self.assertEqual(len(plan['inherited']),19)
        self.assertEqual(list(plan['continuations']),['smdd_004_ABL1_11'])
        self.assertEqual(len(plan['not_started']),320)

if __name__=='__main__':unittest.main()
