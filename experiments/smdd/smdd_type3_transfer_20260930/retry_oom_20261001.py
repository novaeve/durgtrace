from pathlib import Path
import os,json,time,inspect,ast,fcntl,shutil,subprocess,sys,traceback
import runtime
import evaluate as evaluator
from runtime import ROOT,dump
RETRY=ROOT/'reassessment_20261001';RETRY.mkdir(exist_ok=True)
CASES=[('deepseek','smdd_003_6ME6_0'),('deepseek','smdd_003_5UEN_1'),('deepseek','smdd_003_5DC8_0'),('chatdrug','smdd_003_5UEN_1'),('agentdrug','smdd_003_6ME6_0'),('agentdrug','smdd_003_5DC8_2'),('agentdrug','smdd_003_5DC8_0')]

def summary():
 s={}
 for m in ['deepseek','chatdrug','agentdrug']:
  rows=[json.loads(p.read_text()) for p in (ROOT/'evaluation'/m).glob('*/result.json')]
  s[m]={'expected':52,'evaluated':len(rows),**{k:sum(x['status']==k for x in rows) for k in ['passed','failed','errored']}}
 dump(ROOT/'evaluation/summary.json',s)

def work():
 lock=(RETRY/'worker.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 # Preserve raw evaluator evidence before applying the user's invalid-molecule rule.
 invalid=ROOT/'evaluation/chatdrug/smdd_003_6ME6_0/result.json'
 original=json.loads(invalid.read_text())
 backup=RETRY/'original/chatdrug/smdd_003_6ME6_0/result.json'
 if not backup.exists():dump(backup,original)
 assert any(s['name']=='Validity' and s['status']=='failed' for s in original['steps'])
 original.update(status='failed',adjudication={'reason':'Invalid molecule; user instructed to count as failure','time':time.time(),'raw_result':str(backup),'remaining_metric_errors_preserved':True})
 dump(invalid,original);summary()
 # Change only deployment batch size; official evaluator and scoring functions are unchanged.
 gpu_source=inspect.getsource(runtime.gpu_run)
 assert "'--max_parallel_samples','2'" in gpu_source
 gpu_source=gpu_source.replace("'--max_parallel_samples','2'","'--max_parallel_samples','1'").replace('>=20000','>=28000')
 ns=dict(runtime.__dict__);exec(compile(gpu_source,'<boltz_retry_parallel1>','exec'),ns)
 eval_source=inspect.getsource(evaluator.evaluate)
 needle="ev=ROOT/'evaluation'/method/tid"
 assert needle in eval_source
 eval_source=eval_source.replace(needle,"ev=ROOT/'reassessment_20261001'/method/tid")
 ens=dict(evaluator.__dict__);ens['gpu_run']=ns['gpu_run'];exec(compile(eval_source,'<independent_retry_evaluator>','exec'),ens)
 dump(RETRY/'manifest.json',{'cases':CASES,'gpu':os.environ['SMDD_TYPE3_GPU'],'max_parallel_samples':1,'diffusion_samples':10,'diffusion_samples_affinity':10,'seed':42,'thresholds':'unchanged','generated_solutions':'unchanged'})
 rows=[]
 for method,tid in CASES:
  source=ROOT/'evaluation'/method/tid/'result.json'
  orig=json.loads(source.read_text());saved=RETRY/'original'/method/tid/'result.json'
  if not saved.exists():
   assert orig['status']=='errored';dump(saved,orig)
  dump(RETRY/'progress.json',{'status':'running','current':method+'/'+tid,'completed':len(rows),'expected':7,'results':rows})
  try:
   if shutil.disk_usage(ROOT).free<10*1024**3:raise RuntimeError('Insufficient free disk for safe retry')
   result=ens['evaluate'](tid,method)
   if result['status']!='errored':
    result['reassessment']={'raw_result':str(saved),'retry_directory':str(RETRY/method/tid),'max_parallel_samples':1,'time':time.time()}
    dump(source,result)
   row={'method':method,'task':tid,'status':result['status']}
  except Exception as exc:row={'method':method,'task':tid,'status':'errored','error':str(exc)}
  rows.append(row);summary();print(json.dumps(row),flush=True)
 dump(RETRY/'progress.json',{'status':'complete' if all(x['status']!='errored' for x in rows) else 'needs_attention','completed':len(rows),'expected':7,'results':rows})

if __name__=='__main__':
 if '--work' in sys.argv:work()
 else:
  pidfile=RETRY/'worker.pid'
  if pidfile.exists():
   p=Path('/proc')/pidfile.read_text().strip()/'stat'
   if p.exists() and p.read_text().split()[2]!='Z':raise RuntimeError('Retry already running')
  env=dict(os.environ,SMDD_TYPE3_GPU='5',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
  with (RETRY/'worker.log').open('a') as log:
   proc=subprocess.Popen([sys.executable,__file__,'--work'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  pidfile.write_text(str(proc.pid));time.sleep(3);assert proc.poll() is None,(RETRY/'worker.log').read_text()[-1500:]
  print(json.dumps({'pid':proc.pid,'progress':json.loads((RETRY/'progress.json').read_text())}))
