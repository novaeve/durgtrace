import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from guard import python_reason,reason
from oracle_server import OracleService
from scp_gateway import SCPGateway,charge_molecules
from validation import final_answer,audit


class Regressions(unittest.TestCase):
    def test_01_count_duplicates_invalid_and_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=OracleService(tmp,'qed',3,lambda s:0.5)
            r=service.score(['CCO','OCC','invalid','CCC'])
            self.assertEqual([x['status'] for x in r['results']],['new','duplicate','invalid'])
            self.assertEqual(r['not_evaluated'],1)
            self.assertEqual(OracleService(tmp,'qed',3,lambda s:0.5).score(['CC'])['results'],[])

    def test_02_external_scoring_shares_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=OracleService(tmp,'qed',3,lambda s:0.5)
            service.score(['CCO'])
            service.score_external(['CCO','CC'],'scp_calculate_mol_drug_chemistry')
            with self.assertRaises(ValueError):service.score_external(['CCC'],'external')
            self.assertEqual(len(service.ledger().rows),3)

    def test_03_external_batch_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=OracleService(tmp,'qed',2,lambda x:0.5)
            with self.assertRaises(ValueError):s.score_external(['CC','CCC','CCCC'],'external')
            self.assertEqual(len(s.ledger().rows),0)

    def test_04_concurrent_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            def work(i):return OracleService(tmp,'qed',17,lambda s:0.5).score(['CCO']*7)
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(work,range(10)))
            rows=OracleService(tmp,'qed',17,lambda s:0.5).ledger().rows
            self.assertEqual(len(rows),17);self.assertEqual([r['index'] for r in rows],list(range(1,18)))

    def test_05_version_check_allowed(self):
        self.assertIsNone(python_reason('from rdkit import Chem\nfrom rdkit.Chem import QED\nprint(__import__("rdkit").__version__)'))
        self.assertIsNotNone(python_reason('from rdkit.Chem import QED\nQED.qed(m)'))
        self.assertIsNotNone(python_reason('from rdkit.Chem.QED import qed as f\nf(m)'))

    def test_06_valsartan_reconstruction_blocked(self):
        code='from rdkit.Chem import Crippen,rdMolDescriptors\nimport math\ndef sc(m):\n return math.exp(-0.5*((Crippen.MolLogP(m)-2.016)/0.2)**2)\nsc(m)'
        self.assertIsNotNone(python_reason(code))
        self.assertIsNotNone(python_reason('import math\nprint(math.exp(-0.5*((4.1-2.016)/0.2)**2))'))
        self.assertIsNone(python_reason('from rdkit import Chem\nfrom rdkit.Chem import Crippen\nprint(Crippen.MolLogP(Chem.MolFromSmiles("CCO")))'))

    def test_07_fixed_workspace_after_cd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cwd=root/'.claude/skills';cwd.mkdir(parents=True)
            prev=os.environ.get('PMO_WORKSPACE_ROOT');os.environ['PMO_WORKSPACE_ROOT']=str(root)
            try:
                self.assertIsNone(reason({'tool_name':'Write','cwd':str(cwd),'tool_input':{'file_path':str(root/'result.md'),'content':'QED and similarity results'}}))
                self.assertIsNone(reason({'tool_name':'Bash','cwd':str(cwd),'tool_input':{'command':'pwd'}}))
            finally:
                if prev is None:os.environ.pop('PMO_WORKSPACE_ROOT',None)
                else:os.environ['PMO_WORKSPACE_ROOT']=prev

    def test_08_generation_is_not_similarity_scoring(self):
        args={'smiles':'CCO','n':10,'min_similarity':0.5,'prior_type':'similarity'}
        self.assertEqual(charge_molecules('gsk3b','reinvent_mol2mol_sampling',args),[])
        self.assertEqual(charge_molecules('qed','calculate_mol_drug_chemistry',{'smiles_list':['CCO']}),['CCO'])

    def test_09_summary_is_not_final(self):
        for text in ['<summary>Submit <answer>CCO</answer></summary>','<answer>...</answer>','I will generate candidates next.','<answer>CCO</answer><answer>CCC</answer>']:
            self.assertIsNone(final_answer(text))
        self.assertEqual(final_answer('Finished.\n<answer>CCO</answer>'),'CCO')

    def test_10_python_heredoc_and_written_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            data={'tool_name':'Bash','cwd':tmp,'tool_input':{'command':"cat > x.py <<'EOF'\nfrom rdkit.Chem import QED\nprint(QED.qed(m))\nEOF\npython3 x.py"}}
            self.assertIsNotNone(reason(data))
            data['tool_input']['command']="python3 <<'EOF'\nfrom rdkit import Chem\nprint(Chem.MolToSmiles(Chem.MolFromSmiles('CCO')))\nEOF"
            self.assertIsNone(reason(data))

    def test_11_gateway_charges_and_does_not_call_at_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=SCPGateway.__new__(SCPGateway);gateway.out=Path(tmp);gateway.task='qed';gateway.ready=True
            gateway.oracle=OracleService(tmp,'qed',1,lambda x:0.5);calls=[]
            def remote(method,params):calls.append(params);return {'content':[{'type':'text','text':'{"qed":0.5}'}]}
            gateway.remote=remote
            req={'method':'tools/call','params':{'name':'calculate_mol_drug_chemistry','arguments':{'smiles_list':['CCO']}}}
            first=gateway.handle(req);self.assertFalse(first.get('isError',False),first);self.assertEqual(len(calls),1)
            second=gateway.handle(req);self.assertTrue(second['isError']);self.assertEqual(len(calls),1)

    def test_12_receipt_audit_detects_missing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=OracleService(tmp,'qed',1000,lambda x:0.5);rows=service.score(['CCO'])['results']
            self.assertFalse(audit(Path(tmp),service.ledger())['passed'])
            record={'server':'OracleService','result':{'content':[{'type':'text','text':json.dumps({'results':rows})}]}}
            (Path(tmp)/'mcp_receipts.jsonl').write_text(json.dumps(record)+'\n')
            self.assertTrue(audit(Path(tmp),service.ledger())['passed'])

    def test_13_cli_tool_result_file_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'sample';control=base/'control';root.mkdir()
            saved={k:os.environ.get(k) for k in ('PMO_WORKSPACE_ROOT','PMO_CONTROL_DIR')}
            os.environ.update(PMO_WORKSPACE_ROOT=str(root),PMO_CONTROL_DIR=str(control))
            try:
                p=control/'.runtime/projects/sample/session/tool-results/output.txt'
                self.assertIsNone(reason({'tool_name':'Read','cwd':str(root),'tool_input':{'file_path':str(p)}}))
                self.assertIsNotNone(reason({'tool_name':'Read','cwd':str(root),'tool_input':{'file_path':str(control/'oracle_queries.jsonl')}}))
            finally:
                for k,v in saved.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v

    def test_14_summary_resumes_same_episode_without_charging(self):
        import runner
        commands=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def service(out,task):return OracleService(out,task,1000,lambda x:0.5)
            def setup(task,out,control):
                service(control,task).score(['CCO'],'initial_model_answer')
                return 'Task'
            def execute(control,command,**kwargs):
                commands.append(command)
                if len(commands)==3:
                    c=root/'control/qed/0'
                    rows=service(c,'qed').score(['CCO']*999)['results']
                    record={'server':'OracleService','result':{'content':[{'type':'text','text':json.dumps({'results':rows})}]}}
                    (c/'mcp_receipts.jsonl').write_text(json.dumps(record)+'\n')
                if len(commands)==1:
                    text='<summary>Pending: submit <answer>...</answer></summary>'
                else:
                    (Path(kwargs['cwd'])/'result.md').write_text('Completed original episode.')
                    text='<answer>CCO</answer>'
                kwargs['stdout'].write(json.dumps({'type':'result','is_error':False,'result':text})+'\n')
                return SimpleNamespace(returncode=0,stalled=False)
            with patch.object(runner,'ROOT',root),patch.object(runner,'setup',setup),patch.object(runner,'OracleService',service),patch.object(runner,'run_native',execute):
                result=runner.job('qed')
            self.assertEqual(result['status'],'validated_finished')
            self.assertEqual(result['oracle_submissions'],1000)
            self.assertEqual(result['recovery_segments'],2)
            first_id=commands[0][commands[0].index('--session-id')+1]
            resumed_id=commands[1][commands[1].index('--resume')+1]
            self.assertEqual(first_id,resumed_id)


if __name__=='__main__':unittest.main(verbosity=2)
