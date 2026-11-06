"""Prompt-only tests: no gold file is permitted to be opened by this process."""
import json,sys,tempfile
from pathlib import Path
import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem
import public_checks as c
import run_agents as a
from transport import dump

def forbid_gold(event,args):
 if event=='open' and isinstance(args[0],(str,bytes)) and 'answers.json' in str(args[0]):raise AssertionError('Gold answer access forbidden in generation tests')
sys.addaudithook(forbid_gold)

def edit(text,sm):return {'task':'edit','edit_instructions':text,'original_smiles':sm}
def generation(text):return {'task':'generation','structure_description':text}

def main():
 p=c.compile_case(edit('Exchange all fluorine atoms in the molecule for chlorine atoms.','FC(F)C'))
 assert p['complete_task_verifier']
 assert c.assess(p,'ClC(Cl)C')['task_status']=='verified_pass'
 assert c.assess(p,'FC(Cl)C')['task_status']=='verified_fail'
 p=c.compile_case(edit('Deprotonate the amino group to yield a neutral molecule.','CC[NH3+]'))
 assert c.assess(p,'CCN')['checked_pass'] and not c.assess(p,'CC[NH3+]')['checked_pass']
 assert not p['complete_task_verifier']
 p=c.compile_case(edit('Remove the hydroxyl group from the ring.','OC1CC(O)CCC1'))
 assert c.assess(p,'OC1CCCCC1')['task_status']=='partial_pass_unverified'
 assert not c.assess(p,'C1CCCCC1')['checked_pass']
 p=c.compile_case(edit('Relocate the hydroxyl group to another position.','CC(O)CC'))
 assert c.assess(p,'CCCCO')['checked_pass']
 assert not c.assess(p,'CCCC')['checked_pass']
 p=c.compile_case(generation('The molecule contains no carbon atoms and no rings.'))
 assert c.assess(p,'NN')['checked_pass'] and not c.assess(p,'CC')['checked_pass']
 p=c.compile_case(generation('A benzene ring bears three fluorine atoms. Another benzene ring bears one fluorine atom.'))
 f=[r for r in p['rules'] if r['property']=='atom_F'];assert len(f)==1 and f[0]['operator']=='ge' and f[0]['target']==3
 assert c.assess(p,'Fc1cc(F)cc(F)c1')['task_status']=='partial_pass_unverified'
 # Template-only data and poisoning an unrelated key must not alter the plan.
 cases=json.loads((a.ROOT/'data/cases.json').read_text())
 for case in cases:
  assert c.compile_case(case)==c.compile_case({**case,'ignored_fake_gold':'THIS MUST NEVER BE READ'})
 # Exercise original native loops with a partial-pass output; they must not stop
 # as though the entire task had been verified.
 case={'id':'synthetic','task':'generation','structure_description':'The molecule contains one oxygen atom.','prompt':'The molecule contains one oxygen atom. Return the resulting SMILES string enclosed within <smiles> and </smiles> tags.'}
 a.PLANS={'synthetic':c.compile_case(case)}
 sm='CCCCCCCCO';m=Chem.MolFromSmiles(sm)
 lib={'db':pd.DataFrame({'SMILES':[sm],'mol':[m],'fp':[AllChem.GetMorganFingerprint(m,2)]}),'props':[c.descriptors(sm)]}
 a.LIBS={'chatdrug':lib,'agentdrug':lib}
 class Fake:
  def __init__(self,method):self.calls=[];self.method=method
  def complete(self,messages,label,cap=None):
   self.calls.append({'messages':json.loads(json.dumps(messages)),'cap':cap})
   return '- CCCCCC(O)C' if self.method=='chatdrug' else 'CCCCCC(O)C'
 for method,expected in [('chatdrug',3),('agentdrug',5)]:
  with tempfile.TemporaryDirectory() as folder:
   relay=Fake(method);sm,details=getattr(a,method)(case,relay,Path(folder))
   assert len(relay.calls)==expected,(method,details)
   feedback=relay.calls[1]['messages'][-1]['content']
   assert 'NOT verified' in feedback and 'implemented checks only' in feedback
   assert 'is correct and similar' not in feedback
 report={'public_cases_audited':len(cases),'synthetic_semantics_tests':6,'gold_access_forbidden':True,'partial_pass_does_not_stop_agent':True}
 dump(a.ROOT/'public_feedback_validation.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
