"""Fresh uncapped calls for the approved 1120 cases; preserve all other results."""
import collections,concurrent.futures,fcntl,hashlib,importlib.util,json,os,shutil,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DIRECT=ROOT.parent;EXPERIMENT=DIRECT.parent
sys.path.insert(0,str(ROOT))
from common import dump
manifest=json.loads((ROOT/'manifest.json').read_text());jobs=json.loads((ROOT/'jobs.json').read_text())
assert len(jobs)==1120 and hashlib.sha256((ROOT/'jobs.json').read_bytes()).hexdigest()==manifest['jobs_sha256']
assert hashlib.sha256((ROOT/'request_impl.py').read_bytes()).hexdigest()==manifest['helper_sha256']
spec=importlib.util.spec_from_file_location('frozen_single_request',ROOT/'request_impl.py')
impl=importlib.util.module_from_spec(spec);spec.loader.exec_module(impl);impl.ROOT=ROOT
old_body=impl.request_body
def uncapped_body(case):
 body=old_body(case);body.pop('max_tokens',None);body.pop('max_completion_tokens',None)
 assert len(body['messages'])==1 and body['n']==1 and 'tools' not in body
 return body
impl.request_body=uncapped_body

def execute(job):
 if (EXPERIMENT/'provider_hold.json').exists():raise RuntimeError('PROVIDER_HOLD')
 row=impl.run_one(job);path=ROOT/'runs/GLM_direct'/job['setting']/job['case']['id']
 receipt=json.loads((path/'api.json').read_text())
 assert receipt['request']==uncapped_body(job['case']) and receipt['started']>=manifest['created']
 assert receipt['response']['model']=='glm-5.3-flash'
 row.update(retry_run_id=manifest['run_id'],output_budget=manifest['output_budget'],retry_reason='2048-token truncation')
 dump(path/'result.json',row)
 return row

def promote(job,row):
 source=ROOT/'runs/GLM_direct'/job['setting']/job['case']['id']
 target=DIRECT/'runs/GLM_direct'/job['setting']/job['case']['id']
 old=json.loads((target/'result.json').read_text())
 if old.get('retry_run_id')==manifest['run_id']:return
 assert old['status']=='provider_limit','Refuse to replace a non-target scientific result'
 archive=ROOT/'previous_capped_results'/job['setting']/job['case']['id'];archive.mkdir(parents=True,exist_ok=True)
 for name in ('api.json','result.json'):
  shutil.copy2(target/name,archive/name)
  assert (archive/name).read_bytes()==(target/name).read_bytes()
  temporary=target/(name+'.retry1120.tmp');shutil.copy2(source/name,temporary);temporary.replace(target/name)

def snapshot(phase,rows,errors=None):
 state={'phase':phase,'processed':len(rows),'expected':1120,'workers':16,'run_id':manifest['run_id'],
  'success':sum(r['score']['success'] for r in rows.values()),
  'statuses':dict(collections.Counter(r['status'] for r in rows.values())),
  'output_budget':manifest['output_budget'],'time':time.time()}
 if errors:state['errors']=errors
 dump(ROOT/'state.json',state);dump(ROOT/'summary.json',state);print(json.dumps(state),flush=True)

def main():
 with (ROOT/'run.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  rows={};snapshot('pilot',rows)
  for phase,batch in [('pilot',jobs[:20]),('full',jobs[20:])]:
   errors=[]
   with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    futures={pool.submit(execute,job):job for job in batch}
    for future in concurrent.futures.as_completed(futures):
     if future.cancelled():continue
     job=futures[future]
     try:
      row=future.result();rows[(row['setting'],row['id'])]=row
      if phase=='full':promote(job,row)
     except Exception as error:
      errors.append({'id':job['case']['id'],'setting':job['setting'],'error':str(error)})
      for queued in futures:queued.cancel()
     if errors or len(rows)%10==0:snapshot(phase,rows,errors)
   if errors:
    snapshot('awaiting_quota' if any('PROVIDER_HOLD' in e['error'] for e in errors) else 'attention_required',rows,errors);return 1
   if phase=='pilot':
    evidence=[]
    for job in batch:
     row=rows[(job['setting'],job['case']['id'])]
     receipt=json.loads((ROOT/'runs/GLM_direct'/job['setting']/job['case']['id']/'api.json').read_text())
     evidence.append({'id':row['id'],'status':row['status'],'finish_reason':row['finish_reason'],
      'content_length':len(row['output'] or ''),'usage':receipt['response'].get('usage'),
      'request_id':row['request_id']})
    accepted=all(r['status']!='provider_limit' for r in rows.values())
    dump(ROOT/'pilot_acceptance.json',{'accepted':accepted,'episodes':20,'evidence':evidence,'time':time.time()})
    if not accepted:snapshot('attention_required',rows,[{'error':'Provider-default budget still truncates pilot'}]);return 1
    for job in batch:promote(job,rows[(job['setting'],job['case']['id'])])
    snapshot('full',rows)
  hashes=json.loads((ROOT/'preserved_non_target_hashes.json').read_text())
  for path,digest in hashes.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Non-target result changed'
  assert len(rows)==1120
  dump(ROOT/'preservation_audit.json',{'verified_unchanged_non_target_results':len(hashes),'replaced_only_selected_cases':1120,'time':time.time()})
  # Rebuild canonical summary from formal results; generation on other cases is unchanged.
  allrows=[json.loads(p.read_text()) for p in (DIRECT/'runs/GLM_direct').glob('*/*/result.json')]
  alljobs=json.loads((DIRECT/'jobs.json').read_text());groups=[]
  for (setting,prop),n in collections.Counter((j['setting'],j['case']['property']) for j in alljobs).items():
   rr=[r for r in allrows if r['setting']==setting and r['case']['property']==prop]
   groups.append({'setting':setting,'property':prop,'expected':n,'processed':len(rr),'success':sum(r['score']['success'] for r in rr),'statuses':dict(collections.Counter(r['status'] for r in rr))})
  dump(DIRECT/'summary.json',{'method':'GLM_direct','processed':len(allrows),'expected':4200,'groups':groups,'uncapped_retry_cases':1120,'updated':time.time()})
  snapshot('complete',rows);return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as error:
  dump(ROOT/'state.json',{'phase':'attention_required','error':str(error),'expected':1120,'workers':16,'time':time.time()});raise
