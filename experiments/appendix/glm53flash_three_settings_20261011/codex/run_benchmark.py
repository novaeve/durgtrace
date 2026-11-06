"""4200 frozen jobs through the DeepSeek-control native Codex harness with GLM."""
import collections,concurrent.futures,fcntl,hashlib,importlib.util,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EXPERIMENT=ROOT.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'native'))
from common import score,dump
MODEL='glm-5.3-flash';WORKERS=int(os.environ.get('MOL_BENCH_WORKERS','64'))
JOBS=json.loads((ROOT/'jobs.json').read_text())
spec=importlib.util.spec_from_file_location('frozen_native_codex',ROOT/'native/run.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
def native_dir(j):return ROOT/'native/runs'/j['setting']/j['case']['id']
def final_dir(j):return ROOT/'runs/Codex'/j['setting']/j['case']['id']
def validate():
 m=json.loads((ROOT/'manifest.json').read_text())
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 for p,h in m['source_pins'].items():assert sha(p)==h,p
 assert sha(m['cli_binary'])==m['cli_sha256']
 assert sha(ROOT/'jobs.json')==m['jobs_sha256'] and sha(ROOT/'common.py')==m['common_sha256']
 for j in JOBS:
  assert not score(j['case'],j['case']['smiles'])['success']
  assert not score(j['case'],None)['success']
 return m
def records(j):
 result=[]
 for p in sorted((native_dir(j)/'api').glob('*.json')):
  try:result.append(json.loads(p.read_text()))
  except ValueError:pass
 return result
def infrastructure(j,row):
 if row.get('status')=='interrupted':return True
 if row.get('status')!='error':return False
 aa=records(j)
 return any(a.get('error_status') in (408,429,500,502,503,504,529) or any(s in str(a.get('error','')) for s in ('ConnectionError','Timeout','incomplete_provider_stream')) for a in aa[-1:])
def archive(j,label):
 target=ROOT/'recovery_archive'/j['setting']/j['case']['id']/(time.strftime('%Y%m%dT%H%M%S')+'_'+str(label))
 target.mkdir(parents=True,exist_ok=False)
 for name,p in [('native',native_dir(j)),('work',ROOT/'native/work'/j['setting']/j['case']['id']),('final',final_dir(j))]:
  if p.exists():
   assert p.resolve().is_relative_to(ROOT.resolve());p.rename(target/name)
 return str(target)
def execute(j):
 fp=final_dir(j)/'result.json'
 if fp.exists():return json.loads(fp.read_text())
 while (EXPERIMENT/'provider_hold.json').exists():time.sleep(2)
 c=j['case'];case=dict(c,bench=c['benchmark'],bucket=str(c['task'])+'_'+c['constraint'],index=int(c['id'].rsplit('_',1)[1]))
 history=[]
 for attempt in range(3):
  row=native.execute(case,j['setting'])
  retryable=infrastructure(j,row)
  if retryable and attempt<2:
   history.append(archive(j,'infra_'+str(attempt)));time.sleep(5*(attempt+1));continue
  break
 result=dict(row,case=c,setting=j['setting'],method='Codex',model=MODEL,retryable=retryable,recovery_archives=history,
             native_result=str(native_dir(j)/'result.json'),finished=time.time())
 result['score']=score(c,row.get('candidate') if row.get('status')=='complete' else None)
 dump(fp,result);print(json.dumps({k:result.get(k) for k in ('id','setting','status','error')}),flush=True)
 return result
def summary():
 rows=[json.loads(p.read_text()) for p in (ROOT/'runs/Codex').glob('*/*/result.json')]
 groups=[]
 for (setting,prop),n in collections.Counter((j['setting'],j['case']['property']) for j in JOBS).items():
  rr=[r for r in rows if r['setting']==setting and r['case']['property']==prop]
  groups.append(dict(setting=setting,property=prop,expected=n,processed=len(rr),success=sum(r['score']['success'] for r in rr),statuses=dict(collections.Counter(r['status'] for r in rr))))
 report=dict(method='Codex',model=MODEL,processed=len(rows),expected=4200,workers=WORKERS,groups=groups,updated=time.time())
 dump(ROOT/'summary.json',report);return report
def ordered():
 buckets=collections.defaultdict(list)
 for j in JOBS:buckets[(j['setting'],j['case']['task'],j['case']['constraint'])].append(j)
 assert len(buckets)==20
 for b in buckets.values():b.sort(key=lambda j:j['case'].get('original_row',int(j['case']['id'].rsplit('_',1)[1])))
 ordered=[b[i] for i in range(max(map(len,buckets.values()))) for b in buckets.values() if i<len(b)]
 assert len(ordered)==4200;return ordered[:20],ordered[20:]
def batch(jobs):
 pending_jobs=iter(j for j in jobs if not (final_dir(j)/'result.json').exists())
 completed=0
 with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
  pending=set()
  for _ in range(WORKERS):
   j=next(pending_jobs,None)
   if j:pending.add(pool.submit(execute,j))
  while pending:
   done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
   for f in done:
    f.result();pending.remove(f);completed+=1
    if completed%5==0:summary()
    j=next(pending_jobs,None)
    if j:pending.add(pool.submit(execute,j))
 return summary()
def pilot_check(jobs):
 evidence=[]
 for j in jobs:
  r=json.loads((final_dir(j)/'result.json').read_text());assert r['status'] not in ('error','interrupted'),r.get('error')
  assert j['case']['instruction'] in (native_dir(j)/'prompt.txt').read_text()
  aa=records(j);real=[a for a in aa if a.get('response')]
  assert real,'Missing real model response'
  for a in real:
   assert a['request']['model']==a['response']['model']==MODEL
   assert a['request']['reasoning_effort']=='low' and a['request']['temperature']==0
   assert 'max_tokens' not in a['request'] and 'max_completion_tokens' not in a['request']
  evidence.append({'id':r['id'],'setting':j['setting'],'status':r['status'],'provider_calls':len(real),'tool_calls':r.get('tool_calls')})
 dump(ROOT/'pilot_acceptance.json',{'accepted':True,'episodes':20,'evidence':evidence,'time':time.time()})
def main():
 validate()
 if '--check' in sys.argv:
  dump(ROOT/'offline_validation.json',{'passed':True,'cases':4200,'native_binary_verified':True,'scoring_verified':True})
  print('CODEX_OFFLINE_VALIDATION_PASSED',flush=True);return
 if '--smoke' in sys.argv:
  c=dict(JOBS[0]['case'],id='synthetic_native_smoke',bench='ChatDrug',bucket='probe',index=0)
  row=native.execute(c,'preflight',prompt_override='Use your shell tool to run Python, import rdkit, compute 17*19, and write the result to probe.txt. Read it back with a shell tool. Finish saying SMOKE_OK. Work only in /workspace.')
  assert row['status']=='complete' and row.get('tool_calls',0)>=1,row
  assert (ROOT/'native/work/preflight/synthetic_native_smoke/probe.txt').read_text().strip()=='323'
  aa=[json.loads(p.read_text()) for p in (ROOT/'native/runs/preflight/synthetic_native_smoke/api').glob('*.json')]
  assert any(a.get('response',{}).get('model')==MODEL for a in aa)
  dump(ROOT/'native_smoke.json',dict(passed=True,tools=row['tool_calls'],model=MODEL,time=time.time()))
  print('NATIVE_CODEX_GLM_SHELL_SMOKE_PASSED',flush=True);return
 with (ROOT/'run.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  pilot,full=ordered();dump(ROOT/'state.json',{'phase':'pilot','model':MODEL,'workers':WORKERS,'time':time.time()})
  batch(pilot);pilot_check(pilot)
  dump(ROOT/'state.json',{'phase':'full','model':MODEL,'workers':WORKERS,'time':time.time()});batch(full)
  for sweep in range(3):
   retry=[]
   for j in JOBS:
    r=json.loads((final_dir(j)/'result.json').read_text())
    if r['status'] in ('error','interrupted') and r.get('retryable'):archive(j,'sweep_'+str(sweep));retry.append(j)
   if not retry:break
   batch(retry)
  report=summary();assert report['processed']==4200
  errors=sum(json.loads(p.read_text())['status'] in ('error','interrupted') for p in (ROOT/'runs/Codex').glob('*/*/result.json'))
  dump(ROOT/'state.json',dict(phase='attention_required' if errors else 'complete',processed=4200,expected=4200,error_count=errors,workers=WORKERS,time=time.time()))
if __name__=='__main__':
 os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
 try:main()
 except Exception as e:
  dump(ROOT/'state.json',dict(phase='failed',error=str(e),workers=WORKERS,time=time.time()))
  (ROOT/'pipeline_error.log').write_text(traceback.format_exc());raise
