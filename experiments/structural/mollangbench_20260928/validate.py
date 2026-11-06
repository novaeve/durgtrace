"""Exercise the original full evaluator on a mocked local dataset, without API."""
import json,tempfile,typing,re
from pathlib import Path
import pandas as pd
from rdkit import Chem
from transport import functions,dump
import score
ROOT=Path(__file__).resolve().parent
def main():
 cases=json.loads((ROOT/'data/cases.json').read_text());answers=json.loads((ROOT/'data/answers.json').read_text());checked=0
 for task in ['edit','generation']:
  for split in ['test','extended']:
   subset=[c for c in cases if c['task']==task and c['split']==split];assert len(subset)==200
   gt=[{('edited_smiles' if task=='edit' else 'smiles'):answers[c['id']]} for c in subset]
   ns={'Chem':Chem,'re':re,'Optional':typing.Optional,'Dict':typing.Dict,'json':json,'tqdm':lambda x,**kw:x,'load_dataset':lambda *args,**kwargs:gt,'print':lambda *a,**kw:None}
   fn='evaluate_editing_results' if task=='edit' else 'evaluate_generation_results'
   functions(score.SOURCE,['canonicalize_smiles','parse_smiles_from_output',fn],ns)
   expected=0;rows=[]
   for i,c in enumerate(subset):
    raw='<smiles>'+answers[c['id']]+'</smiles>' if i%2==0 else '<smiles>invalid</smiles>'
    parsed=score.parse({'body':{'choices':[{'message':{'content':raw}}]}})
    pred=score.canonical(parsed);expected+=pred is not None and pred==score.canonical(answers[c['id']])
    rows.append({'custom_id':f'{task}_{split}_{i}','response':{'body':{'choices':[{'message':{'content':raw}}]}}})
   with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'results.jsonl';p.write_text('\n'.join(json.dumps(r) for r in rows))
    result=ns[fn](str(p),split,'smiles');assert result['accuracy']==expected/200,result
   checked+=200
 assert all('edited_smiles' not in c and 'smiles' not in c and 'canary' not in c for c in cases)
 dump(ROOT/'validation.json',{'official_evaluator_cases':checked,'public_cases_exclude_gold_fields':True});print('VALIDATED',checked,flush=True)
if __name__=='__main__':main()
