import json,collections
import runner as r
from rdkit import Chem
v=json.loads((r.ROOT/'validation.json').read_text())
types=collections.Counter()
for x in v['issues']:
 a=Chem.MolFromSmiles(x['input']);b=Chem.MolFromSmiles(x['rebuilt'])
 types['stereochemistry_only' if Chem.MolToSmiles(a,isomericSmiles=False)==Chem.MolToSmiles(b,isomericSmiles=False) else 'connectivity_or_bond_change']+=1
print('ROUNDTRIP',dict(types))
for stage in ['pilot','full']:
 groups={};settings=[]
 for f in (r.ROOT/'runs'/stage).glob('*/result.json'):
  row=json.loads(f.read_text());key='ChatDrug' if row['case']['benchmark']=='ChatDrug' else row['case']['property'];g=groups.setdefault(key,collections.Counter())
  g['processed']+=1;g[row['status']]+=1
  control=row.get('no_modification_control',{});base=r.p.canonical(control.get('candidate')) if control.get('candidate') else None
  input_s=r.p.canonical(row['case']['smiles'])
  proposed=[c for c in row.get('candidates',[]) if r.p.canonical(c['candidate']) not in [base,input_s]]
  g['proposal_pool_success']+=any(c['success'] for c in proposed)
  g['first_proposal_success']+=bool(proposed and proposed[0]['success'])
  g['original_pool_success']+=row.get('candidate_set_success',False)
  g['no_modification_success']+=control.get('success',False)
  g['roundtrip_changed']+=row.get('roundtrip_changed',False)
  g['llm_calls']+=row.get('llm_calls',0)
  g['truncated']+=row.get('truncated_responses',0)
  for k,val in row.get('usage',{}).items():g[k]+=val
  if not settings:
   calls=json.loads((f.parent/'api_calls.json').read_text());settings=[c.get('request_settings') for c in calls]
 result={'groups':groups,'request_settings_example':settings}
 r.dump(r.ROOT/'runs'/stage/'audit.json',result)
 print(stage,json.dumps(result))
print('NAME_CACHE',dict(collections.Counter(x['status'] for x in r.NAMES.values())))
