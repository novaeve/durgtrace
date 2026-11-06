"""Durable frozen MolClaw three-setting run with one official S2-scored submission."""
import collections,concurrent.futures,fcntl,hashlib,importlib.util,json,os,re,shutil,sys,time,traceback
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/data2/chenfuxin/chatdrug_generalization_20260920');sys.path.insert(0,str(ROOT))
from common import score,dump
MODEL='glm-5.3-flash';WORKERS=int(os.environ.get('MOL_BENCH_WORKERS', '16'))
JOBS=json.loads((ROOT/'jobs.json').read_text())
spec=importlib.util.spec_from_file_location('claw_native',ROOT/'claw_native.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
def native_dir(job):return ROOT/'native/MolClaw'/job['setting']/job['case']['id']
def final_dir(job):return ROOT/'runs/MolClaw'/job['setting']/job['case']['id']
def audit(job):
 return [json.loads(p.read_text()) for p in (ROOT/'proxy_audit'/job['setting']/job['case']['id']).glob('*.json')]
def events(job):
 path=native_dir(job)/'events.jsonl';items=[]
 if path.exists():
  for line in path.read_text().splitlines():
   try:items.append(json.loads(line))
   except ValueError:pass
 return items
def transport(job,row):
 if row.get('status')!='error':return False
 receipts=audit(job)
 if any(a.get('status')=='error' and (a.get('status_code') in (408,429,500,502,503,504,529) or any(x in a.get('error_type','') for x in ('Timeout','Connection','RateLimit','ServiceUnavailable','APIError'))) for a in receipts):return True
 nd=native_dir(job)
 diagnostic=(nd/'stderr.log').read_text() if (nd/'stderr.log').exists() else ''
 for e in events(job):
  if e.get('type')=='result':diagnostic+=' '+str(e.get('errors',''))+' '+str(e.get('result',''))
 return any(x in diagnostic.lower() for x in ('request timed out','connection error','connection reset','upstream_stream_error','incomplete_provider_stream','overloaded','rate limit','status 429','status 502','status 503','status 504','econnreset','fetch failed'))
def archive(job,attempt):
 target=ROOT/'recovery_archive'/job['setting']/job['case']['id']/(time.strftime('%Y%m%dT%H%M%S')+'_'+str(attempt))
 target.mkdir(parents=True,exist_ok=False)
 for label,path in [('native',native_dir(job)),('final',final_dir(job)),('proxy_audit',ROOT/'proxy_audit'/job['setting']/job['case']['id'])]:
  if path.exists():
   assert path.resolve().is_relative_to(ROOT.resolve());path.rename(target/label)
 return str(target)
def execute(job):
 fp=final_dir(job)/'result.json'
 if fp.exists():return json.loads(fp.read_text())
 archives=[]
 for attempt in range(3):
  try:
   native.run_case(job['case'],job['setting'])
   row=json.loads((native_dir(job)/'result.json').read_text())
  except Exception as exc:
   row={'id':job['case']['id'],'status':'error','candidate':None,'error':type(exc).__name__}
   dump(ROOT/'exceptions'/job['setting']/(job['case']['id']+'.json'),{'traceback':traceback.format_exc()})
  retryable=transport(job,row)
  if retryable and attempt<2:
   archives.append(archive(job,attempt));time.sleep(10*(attempt+1));continue
  break
 receipts=audit(job)
 result=dict(row,case=job['case'],method='MolClaw',setting=job['setting'],model=MODEL,
  native_result=str(native_dir(job)/'result.json'),retryable=retryable,recovery_archives=archives,finished=time.time(),
  provider_response_models=sorted({str(a['response_model']) for a in receipts if a.get('response_model')}))
 result['score']=score(job['case'],row.get('candidate') if row.get('status')=='complete' else None)
 dump(fp,result)
 print(json.dumps({k:result.get(k) for k in ('id','setting','status','error')},ensure_ascii=False),flush=True)
 return result
def summary():
 rows=[json.loads(p.read_text()) for p in (ROOT/'runs/MolClaw').glob('*/*/result.json')]
 expected=collections.Counter((j['setting'],j['case']['property']) for j in JOBS)
 groups=[]
 for (setting,prop),total in expected.items():
  rr=[r for r in rows if r['setting']==setting and r['case']['property']==prop]
  success=sum(bool(r['score']['success']) for r in rr)
  groups.append({'setting':setting,'property':prop,'expected':total,'processed':len(rr),'success':success,
   'success_rate_full':success/total,'statuses':dict(collections.Counter(r['status'] for r in rr))})
 report={'model':MODEL,'method':'MolClaw','processed':len(rows),'expected':4200,'workers':WORKERS,'groups':groups,'time':time.time()}
 dump(ROOT/'summary.json',report);return report
def ordered():
 buckets=collections.defaultdict(list)
 for job in JOBS:buckets[(job['setting'],job['case']['task'],job['case']['constraint'])].append(job)
 assert len(buckets)==20
 for bb in buckets.values():bb.sort(key=lambda j:j['case'].get('original_row',int(j['case']['id'].rsplit('_',1)[1])))
 ordered=[bb[i] for i in range(max(map(len,buckets.values()))) for bb in buckets.values() if i<len(bb)]
 assert len(ordered)==4200
 return ordered[:20],ordered[20:]
def validate():
 manifest=json.loads((ROOT/'manifest.json').read_text())
 for path,digest in manifest['frozen_dependencies'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
 assert hashlib.sha256((ROOT/'jobs.json').read_bytes()).hexdigest()==manifest['jobs_sha256']
 assert hashlib.sha256((ROOT/'common.py').read_bytes()).hexdigest()==manifest['common_sha256']
 for setting in manifest['settings']:
  cases=json.loads((ROOT/'inputs'/setting/'cases.json').read_text())
  assert cases==[j['case'] for j in JOBS if j['setting']==setting]
 for j in JOBS:
  assert not score(j['case'],j['case']['smiles'])['success']
  assert not score(j['case'],None)['success']
 port=manifest['proxy_port']
 response=requests.get(f'http://127.0.0.1:{port}/health/liveliness',timeout=30)
 assert response.status_code==200,'Dedicated GPT proxy unhealthy'
 cfg=json.loads((ROOT/'proxy_config.yaml').read_text())
 assert cfg['model_list'][0]['litellm_params']['model']=='openai/'+MODEL
 assert cfg['model_list'][0]['litellm_params']['extra_body']['reasoning_effort']=='low'
 return manifest
def batch(selected):
 selected=[j for j in selected if not (final_dir(j)/'result.json').exists()]
 count=0;last=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
  iterator=iter(selected);pending=set()
  for _ in range(WORKERS):
   j=next(iterator,None)
   if j:pending.add(pool.submit(execute,j))
  while pending:
   done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
   for f in done:
    f.result();pending.remove(f);count+=1
    if count%10==0 or time.monotonic()-last>15:summary();last=time.monotonic()
    j=next(iterator,None)
    if j:pending.add(pool.submit(execute,j))
 return summary()
def pilot_check(selected):
 evidence=[];bad=[]
 for job in selected:
  row=json.loads((final_dir(job)/'result.json').read_text())
  if row['status']=='error':bad.append({'id':row['id'],'setting':job['setting'],'error':row.get('error')})
  assert job['case']['instruction'] in (native_dir(job)/'prompt.txt').read_text()
  runtime=next((e for e in events(job) if e.get('type')=='system' and e.get('subtype')=='init'),None)
  assert runtime and runtime.get('model')==MODEL,'Native runtime/model receipt missing'
  assert any(s.get('name')=='molclaw-scp' and s.get('status')=='connected' for s in runtime.get('mcp_servers',[])),'Native MCP server not connected'
  assert any(str(t).startswith('mcp__molclaw-scp__') for t in runtime.get('tools',[])),'Native MCP tools missing'
  receipts=[r for r in audit(job) if r.get('status')=='complete']
  assert receipts,'Per-case GPT provider receipt missing'
  assert all(r['response_model_ok'] for r in receipts),'Provider returned an unexpected model'
  evidence.append({'id':row['id'],'setting':job['setting'],'status':row['status'],'provider_receipts':len(receipts),'model':runtime['model'],'mcp_verified':True})
 dump(ROOT/'pilot_acceptance.json',{'accepted':not bad,'episodes':20,'evidence':evidence,'failures':bad,'time':time.time()})
 assert not bad,'Native pilot infrastructure failure'
def main():
 lock=(ROOT/'run.lock').open('a')
 with lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  validate();pilot,full=ordered()
  if '--check' in sys.argv:
   dump(ROOT/'offline_validation.json',{'passed':True,'cases':4200,'pilot':20,'native_sources_verified':True})
   print('OFFLINE_NATIVE_CHECK_PASSED',flush=True);return
  dump(ROOT/'state.json',{'phase':'pilot','model':MODEL,'workers':WORKERS,'time':time.time()})
  batch(pilot);pilot_check(pilot)
  dump(ROOT/'state.json',{'phase':'full','model':MODEL,'workers':WORKERS,'time':time.time()})
  batch(full)
  for sweep in range(3):
   retry=[]
   for j in JOBS:
    r=json.loads((final_dir(j)/'result.json').read_text())
    if r['status']=='error' and r.get('retryable'):
     archive(j,'supervisor_'+str(sweep));retry.append(j)
   if not retry:break
   batch(retry)
  report=summary();assert report['processed']==4200
  errors=sum(json.loads(p.read_text())['status']=='error' for p in (ROOT/'runs/MolClaw').glob('*/*/result.json'))
  dump(ROOT/'state.json',{'phase':'complete' if not errors else 'attention_required','processed':4200,'expected':4200,'error_count':errors,'model':MODEL,'time':time.time()})
if __name__=='__main__':
 os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
 try:main()
 except Exception as exc:
  dump(ROOT/'state.json',{'phase':'failed','error':str(exc),'model':MODEL,'time':time.time()})
  (ROOT/'pipeline_error.log').write_text(traceback.format_exc());raise
