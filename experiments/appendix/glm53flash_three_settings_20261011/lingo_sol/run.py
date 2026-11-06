"""Durable native pipelines, four workers per method, shared preceding cases."""
import collections,concurrent.futures,fcntl,hashlib,importlib.util,json,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/data2/chenfuxin')
CHAT=BASE/'chatdrug_generalization_20260920'
sys.path.insert(0,str(CHAT));sys.path.insert(0,str(ROOT))
from common import score,dump
from provider import MODEL,catalog
METHOD=sys.argv[1]
assert METHOD in ('MolLingo','SoL-Pi')
WORKERS=int(os.environ.get('MOL_BENCH_WORKERS', '12'))
JOBS=json.loads((ROOT/'jobs.json').read_text())
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def validate():
 manifest=json.loads((ROOT/'manifest.json').read_text())
 for p,h in manifest['frozen_dependencies'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 assert hashlib.sha256((ROOT/'jobs.json').read_bytes()).hexdigest()==manifest['jobs_sha256']
 for j in JOBS:
  assert not score(j['case'],j['case']['smiles'])['success']
  assert not score(j['case'],None)['success']
 return manifest
def initialize():
 global native
 if METHOD=='MolLingo':
  sys.path.insert(0,str(BASE/'molingo_20260922'));sys.path.insert(0,str(ROOT))
  native=load(ROOT/'lingo_native.py','lingo_native')
  native.r.CACHE=ROOT/'cache'
 else:
  sys.path.insert(0,str(ROOT/'sol_pi'))
  native=load(ROOT/'sol_pi/run.py','sol_native')
def native_dir(job):
 return (ROOT/'native/MolLingo' if METHOD=='MolLingo' else ROOT/'sol_pi/runs')/job['setting']/job['case']['id']
def final_dir(job):return ROOT/'runs'/METHOD/job['setting']/job['case']['id']
def case_native(job):
 c=job['case'];s=job['setting']
 if METHOD=='MolLingo':return native.run_case(c,s)
 case=dict(c,bench=c['benchmark'],bucket=str(c['task'])+'_'+c['constraint'],index=int(c['id'].rsplit('_',1)[1]),prompt=c['instruction'])
 return native.execute(case,s)
MARKERS=('HTTP_408','HTTP_429','HTTP_500','HTTP_502','HTTP_503','HTTP_504','HTTP_529','HTTP_404',
 'TRANSPORT_ERROR','NO_CHOICES','NO_TEXT_BLOCK','INVALID_JSON','RETRY_EXHAUSTED','ConnectionError',
 'ConnectTimeout','ReadTimeout','ChunkedEncodingError','upstream_stream_error','incomplete_provider_stream','transient_upstream_http')
def records(job):
 path=native_dir(job)
 if METHOD=='MolLingo':return json.loads((path/'api_calls.json').read_text()) if (path/'api_calls.json').exists() else []
 return [json.loads(p.read_text()) for p in sorted((path/'api').glob('*.json'))]
def infrastructure(job,row):
 if row.get('status')!='error':return False
 errors=[str(row.get('error',''))]+[str(a.get('error','')) for a in records(job)[-1:]]
 return any(m in e for m in MARKERS for e in errors)
def archive(job,attempt):
 target=ROOT/'recovery_archive'/METHOD/job['setting']/job['case']['id']/(time.strftime('%Y%m%dT%H%M%S')+'_'+str(attempt))
 target.mkdir(parents=True,exist_ok=False)
 nd=native_dir(job)
 if nd.exists():
  assert nd.resolve().is_relative_to(ROOT.resolve())
  nd.rename(target/'native')
  if METHOD=='MolLingo' and (target/'native/api_calls.json').exists():
   nd.mkdir(parents=True);shutil.copy2(target/'native/api_calls.json',nd/'api_calls.json')
 if METHOD=='SoL-Pi':
  work=ROOT/'sol_pi/work'/job['setting']/job['case']['id']
  if work.exists():
   assert work.resolve().is_relative_to(ROOT.resolve());work.rename(target/'work')
 fd=final_dir(job)
 if fd.exists():fd.rename(target/'final')
 return str(target)
def execute(job):
 fp=final_dir(job)/'result.json'
 if fp.exists():return json.loads(fp.read_text())
 archives=[]
 for attempt in range(3):
  try:row=case_native(job)
  except Exception as exc:
   row=dict(id=job['case']['id'],status='error',candidate=None,error=type(exc).__name__)
   dump(ROOT/'exceptions'/METHOD/job['setting']/(job['case']['id']+'.json'),{'traceback':traceback.format_exc()})
  retryable=infrastructure(job,row)
  if retryable and attempt<2:
   archives.append(archive(job,attempt));time.sleep(10*(attempt+1));continue
  break
 result=dict(row,case=job['case'],setting=job['setting'],method=METHOD,model=MODEL,native_result=str(native_dir(job)/'result.json'),
  retryable=retryable,recovery_archives=archives,finished=time.time())
 result['score']=score(job['case'],row.get('candidate') if row.get('status')=='complete' else None)
 dump(fp,result)
 print(json.dumps({k:result.get(k) for k in ('id','setting','method','status','error')},ensure_ascii=False),flush=True)
 return result
def summary():
 rows=[json.loads(p.read_text()) for p in (ROOT/'runs'/METHOD).glob('*/*/result.json')]
 expected=collections.Counter((j['setting'],j['case']['property']) for j in JOBS)
 groups=[]
 for (setting,prop),n in expected.items():
  rr=[r for r in rows if r['setting']==setting and r['case']['property']==prop]
  success=sum(bool(r['score']['success']) for r in rr)
  groups.append(dict(setting=setting,property=prop,processed=len(rr),expected=n,success=success,success_rate_full=success/n,
   statuses=dict(collections.Counter(r['status'] for r in rr))))
 report=dict(method=METHOD,processed=len(rows),expected=4200,workers=WORKERS,groups=groups,updated=time.time())
 dump(ROOT/'summaries'/(METHOD+'.json'),report);return report
def ordered():
 buckets=collections.defaultdict(list)
 for j in JOBS:buckets[(j['setting'],j['case']['task'],j['case']['constraint'])].append(j)
 assert len(buckets)==20
 for bucket in buckets.values():bucket.sort(key=lambda j:j['case'].get('original_row',int(j['case']['id'].rsplit('_',1)[1])))
 ordered=[bucket[i] for i in range(max(map(len,buckets.values()))) for bucket in buckets.values() if i<len(bucket)]
 assert len(ordered)==4200
 return ordered[:20],ordered[20:]
def batch(selected):
 pending_cases=[j for j in selected if not (final_dir(j)/'result.json').exists()]
 last=time.monotonic();count=0
 with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
  it=iter(pending_cases);pending=set()
  for _ in range(WORKERS):
   j=next(it,None)
   if j:pending.add(pool.submit(execute,j))
  while pending:
   done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
   for future in done:
    future.result();pending.remove(future);count+=1
    if count%10==0 or time.monotonic()-last>15:summary();last=time.monotonic()
    j=next(it,None)
    if j:pending.add(pool.submit(execute,j))
 return summary()
def pilot_check(selected):
 bad=[];evidence=[]
 for j in selected:
  r=json.loads((final_dir(j)/'result.json').read_text())
  if r['status'] not in ('complete','provider_limit','timeout'):bad.append(dict(id=r['id'],setting=j['setting'],error=r.get('error')))
  aa=records(j)
  if METHOD=='MolLingo':
   real=[a for a in aa if a.get('response_model')]
   assert real or r.get('error'),'No provider receipt'
   for a in real:
    assert a['requested_model']==MODEL and a['request_settings']['max_tokens'] is None
    assert a['request_settings']['reasoning_effort']=='low'
   assert not real or j['case']['instruction'] in real[0]['messages'][0]['content']
  else:
   real=[a for a in aa if a.get('response')]
   for a in aa:
    body=a['request'];assert body['model']==MODEL and body['reasoning_effort']=='low'
    assert 'max_tokens' not in body and 'max_completion_tokens' not in body
   assert j['case']['instruction'] in (native_dir(j)/'prompt.txt').read_text()
   work=ROOT/'sol_pi/work'/j['setting']/j['case']['id']
   loaded=json.loads((work/'.pi/loaded-runtime.json').read_text())
   assert loaded['model']==MODEL and loaded['provider']=='mol-edit-glm53flash'
   for flag in ('actionFusion','observationPack','evidencePreservingReducer','onlineContextCompact'):assert loaded['config'][flag] is True
   assert loaded['config']['evidencePreservingReducerModel']==MODEL
   assert 'obs_recall' in [t['name'] for t in loaded['tools']]
   assert real or r.get('error'),'No provider receipt'
  evidence.append(dict(id=j['case']['id'],setting=j['setting'],status=r['status'],real_responses=len(real)))
 dump(ROOT/'pilot_acceptance'/(METHOD+'.json'),dict(accepted=not bad,episodes=20,evidence=evidence,failures=bad,time=time.time()))
 assert not bad,'Pilot infrastructure failure'
def main():
 validate();initialize()
 if '--check' in sys.argv:
  pilot,full=ordered()
  if METHOD=='SoL-Pi':
   work=ROOT/'preflight/sol_workspace';native.prepare_workspace(work)
   relay=native.Relay(ROOT/'preflight/sol_relay');server=relay.service()
   try:
    result=subprocess.run(native.command(work,server.server_port,models=True),capture_output=True,text=True,timeout=120)
    (ROOT/'preflight/sol_models.log').write_text(result.stdout+'\n'+result.stderr)
    assert result.returncode==0 and MODEL in result.stdout,'Native model registration failed'
   finally:server.shutdown();server.server_close()
  dump(ROOT/'preflight'/(METHOD+'.json'),dict(passed=True,cases=4200,pilot=20))
  print('OFFLINE_NATIVE_CHECK_PASSED '+METHOD,flush=True);return
 lockpath=ROOT/'locks'/(METHOD+'.lock');lockpath.parent.mkdir(exist_ok=True)
 with lockpath.open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  dump(ROOT/'catalog'/(METHOD+'.json'),catalog())
  pilot,full=ordered()
  dump(ROOT/'state'/(METHOD+'.json'),dict(phase='pilot',model=MODEL,workers=WORKERS,time=time.time()))
  batch(pilot);pilot_check(pilot)
  dump(ROOT/'state'/(METHOD+'.json'),dict(phase='full',model=MODEL,workers=WORKERS,time=time.time()))
  batch(full)
  for sweep in range(10):
   retry=[]
   for j in JOBS:
    r=json.loads((final_dir(j)/'result.json').read_text())
    if r['status']=='error' and r.get('retryable'):
     archive(j,'supervisor_'+str(sweep));retry.append(j)
   if not retry:break
   batch(retry);time.sleep(30)
  report=summary();assert report['processed']==4200
  errors=sum(json.loads(p.read_text())['status']=='error' for p in (ROOT/'runs'/METHOD).glob('*/*/result.json'))
  dump(ROOT/'state'/(METHOD+'.json'),dict(phase='attention_required' if errors else 'complete',processed=4200,expected=4200,error_count=errors,model=MODEL,time=time.time()))
if __name__=='__main__':
 os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
 try:main()
 except Exception as exc:
  dump(ROOT/'state'/(METHOD+'.json'),dict(phase='failed',error=str(exc),model=MODEL,time=time.time()))
  (ROOT/(METHOD+'_pipeline_error.log')).write_text(traceback.format_exc());raise
