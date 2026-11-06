"""Freeze exactly the 1120 truncations in the user-approved status snapshot."""
import collections,hashlib,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DIRECT=ROOT/'direct';RETRY=DIRECT/'uncapped_retry1120'
assert ROOT==Path('/data/chenfuxin/glm53flash_three_settings_20261011')
if (RETRY/'manifest.json').exists():
 print('Existing 1120-case retry manifest retained');raise SystemExit(0)
scope=json.loads((ROOT/'retry1120_scope.json').read_text(encoding='utf-8-sig'))
assert sum(g['count'] for g in scope['groups'])==scope['expected']==1120
jobs=json.loads((DIRECT/'jobs.json').read_text());bykey={(j['setting'],j['case']['id']):j for j in jobs}
selected=[]
for group in scope['groups']:
 candidates=[]
 for file in (DIRECT/'runs/GLM_direct'/group['setting']).glob('*/result.json'):
  row=json.loads(file.read_text())
  if row['case']['property']==group['property'] and row['status']=='provider_limit':candidates.append((row['finished'],row['id'],file))
 candidates.sort()
 assert len(candidates)>=group['count']
 for finished,ident,file in candidates[:group['count']]:
  assert finished<=scope['source_snapshot_time'],'Selection falls outside the reported snapshot'
  selected.append(bykey[(group['setting'],ident)])
assert len(selected)==1120 and len({(j['setting'],j['case']['id']) for j in selected})==1120
RETRY.mkdir(parents=True,exist_ok=True)
for name in ('common.py','run.py'):
 shutil.copy2(DIRECT/name,RETRY/('request_impl.py' if name=='run.py' else name))
shutil.copy2(ROOT/'direct_retry1120.py',RETRY/'run_retry.py')
(RETRY/'jobs.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
keys={(j['setting'],j['case']['id']) for j in selected};preserved={}
for file in (DIRECT/'runs/GLM_direct').glob('*/*/result.json'):
 if (file.parent.parent.name,file.parent.name) not in keys:preserved[str(file)]=hashlib.sha256(file.read_bytes()).hexdigest()
(RETRY/'preserved_non_target_hashes.json').write_text(json.dumps(preserved,indent=2))
manifest={'run_id':'uncapped_retry1120_'+str(time.time_ns()),'created':time.time(),'expected':1120,'workers':16,
 'scope':scope,'selection_only':'1120 reported provider_limit cases; no successful or scientific-failure case selected',
 'jobs_sha256':hashlib.sha256((RETRY/'jobs.json').read_bytes()).hexdigest(),
 'helper_sha256':hashlib.sha256((RETRY/'request_impl.py').read_bytes()).hexdigest(),
 'output_budget':'provider_default_no_client_token_cap','prompt_unchanged':True,'temperature':0,'reasoning_effort':'low',
 'no_tools':True,'no_feedback':True,'one_response_per_retry':True,'no_scientific_retry':True,'source_formal_result_root':str(DIRECT)}
(RETRY/'manifest.json').write_text(json.dumps(manifest,indent=2))
(RETRY/'state.json').write_text(json.dumps({'phase':'ready','processed':0,'expected':1120,'workers':16},indent=2))
print(json.dumps({'selected':1120,'snapshot_groups':scope['groups'],'non_target_results_pinned':len(preserved),'source_snapshot_time':scope['source_snapshot_time']}),flush=True)
