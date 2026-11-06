"""Two authorized infrastructure reruns and one frozen-submission rescore."""
from pathlib import Path
import collections,fcntl,hashlib,json,os,runpy,shutil,subprocess,sys,time,traceback

BASE=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004')
BATCH=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import runtime
from gpu_slots import acquire

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
 Path(out).mkdir(parents=True,exist_ok=True)
 with acquire(Path(log_path).parent) as (gpu,descriptors):
  args=[str(runtime.BOLTZ),str(BATCH/'boltz_transport.py'),'predict',str(yaml_path),'--out_dir',str(out),
   '--cache','/data2/chenfuxin/boltz-cache','--use_msa_server','--use_potentials','--diffusion_samples',str(samples),
   '--seed',str(seed),'--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
  runtime.dump(Path(log_path).parent/'boltz_provenance.json',{'argv':args,'gpu':gpu,'batch':str(BATCH),'transport_sha256':sha(BATCH/'boltz_transport.py')})
  with open(log_path,'w') as log:proc=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,pass_fds=descriptors)
  return proc.returncode

runtime.gpu_run=gpu_run

def evaluate(tid,out):
 result=out/'evaluation/result.json'
 if not result.exists():
  proc=subprocess.run([sys.executable,str(BATCH/'driver.py'),'score',tid,str(out)])
  if proc.returncode or not result.exists():raise RuntimeError('Official evaluator produced no result')
 return json.loads(result.read_text())

def promote(tid,mode,out,record,manifest):
 original=BASE/'runs/codex'/tid
 assert sha(original/'record.json')==manifest['tasks'][tid]['record_sha256']
 if mode=='rescore':
  assert sha(original/'solution.smi')==sha(out/'solution.smi')==manifest['tasks'][tid]['submission_sha256']
  (original/'evaluation').rename(BATCH/'original_evaluation'/tid)
  try:(out/'evaluation').rename(original/'evaluation')
  except Exception:
   (BATCH/'original_evaluation'/tid).rename(original/'evaluation');raise
 else:
  original.rename(BATCH/'original_runs'/tid)
  try:out.rename(original)
  except Exception:
   (BATCH/'original_runs'/tid).rename(original);raise
 runtime.dump(original/'record.json',record)
 runtime.dump(original/'retry_provenance.json',{'mode':mode,'batch':str(BATCH),'time':time.time(),'original_record_sha256':manifest['tasks'][tid]['record_sha256'],'fresh_attempt_budget':mode=='rerun','original_preserved':True})

def worker(tid):
 manifest=json.loads((BATCH/'manifest.json').read_text());mode=manifest['tasks'][tid]['mode']
 state=BATCH/'workers'/f'{tid}.json';lock=(BATCH/'workers'/f'{tid}.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if state.exists() and json.loads(state.read_text()).get('published'):return
 runtime.dump(state,{'task':tid,'mode':mode,'status':'running','pid':os.getpid(),'started':time.time()})
 out=BATCH/'runs/codex'/tid
 try:
  if mode=='rerun':
   import run as runner
   runner.ROOT=BATCH  # Output location only; task inputs, CLI and runtime remain canonical.
   runner.configure_gpu()
   agent=runner.job('codex',tid,0)
   score='not_evaluated'
   if (out/'solution.smi').exists():score=evaluate(tid,out)['status']
   record={'method':'codex','task':tid,'agent':agent['status'],'evaluation':score,'completed':time.time()}
   if agent['status']=='error' or score in ['errored','evaluation_missing']:raise RuntimeError('Retry still has infrastructure error; output retained')
  else:
   assert sha(out/'solution.smi')==manifest['tasks'][tid]['submission_sha256']
   score=evaluate(tid,out)['status']
   if score not in ['passed','failed']:raise RuntimeError('Rescore remains errored; canonical result retained')
   record=json.loads((BASE/'runs/codex'/tid/'record.json').read_text());record.update(evaluation=score,completed=time.time())
  promote(tid,mode,out,record,manifest)
  runtime.dump(state,{'task':tid,'mode':mode,'status':'finished','score_status':score,'published':True,'ended':time.time()})
  print('FINISHED',tid,score,flush=True)
 except Exception as exc:
  runtime.dump(state,{'task':tid,'mode':mode,'status':'infrastructure_error','error':repr(exc),'traceback':traceback.format_exc(),'ended':time.time()})
  print('ERROR',tid,repr(exc),flush=True)

def report(manifest):
 states={tid:json.loads((BATCH/'workers'/f'{tid}.json').read_text()) for tid in manifest['tasks'] if (BATCH/'workers'/f'{tid}.json').exists()}
 runtime.dump(BATCH/'status.json',{'time':time.time(),'total':3,'states':states,'running':sum(d['status']=='running' for d in states.values()),'ended':sum(d['status']!='running' for d in states.values())})

def main():
 lock=(BATCH/'driver.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 manifest=json.loads((BATCH/'manifest.json').read_text());children=[]
 for tid in manifest['tasks']:
  log=(BATCH/'logs'/f'{tid}.log').open('a')
  p=subprocess.Popen([sys.executable,str(BATCH/'driver.py'),'worker',tid],stdout=log,stderr=subprocess.STDOUT)
  children.append((p,log))
 while any(p.poll() is None for p,log in children):report(manifest);time.sleep(5)
 for p,log in children:log.close()
 report(manifest)
 untouched={path:h for path,h in manifest['all_terminal_hashes'].items() if Path(path).parent.name not in manifest['tasks'] or '/runs/deepseek/' in '/'+path}
 assert all(sha(BASE/path)==h for path,h in untouched.items())
 assert all(sha(BASE/name)==h for name,h in manifest['source_hashes'].items())
 snapshot=json.loads((BASE/'scheduler_status.json').read_text())
 assert snapshot['state']=='complete' and not any(snapshot['active'].values())
 for method in ['deepseek','codex']:
  rows=[json.loads(p.read_text()) for p in (BASE/'runs'/method).glob('*/record.json')]
  snapshot['counts'][method].update(completed=len(rows),evaluation=dict(collections.Counter(d['evaluation'] for d in rows)),agent=dict(collections.Counter(d['agent'] for d in rows)))
 snapshot.update(updated=time.time(),last_retry_batch=str(BATCH));runtime.dump(BASE/'scheduler_status.json',snapshot)
 runtime.dump(BATCH/'completion.json',{'time':time.time(),'nonselected_records_unchanged':True,'shared_source_files_unchanged':True,'counts':snapshot['counts']['codex']})
 print('BATCH_COMPLETE',json.dumps(snapshot['counts']['codex']),flush=True)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='score':
  sys.argv=[str(BASE/'evaluate.py'),sys.argv[2],sys.argv[3]];runpy.run_path(str(BASE/'evaluate.py'),run_name='__main__')
 elif len(sys.argv)>1 and sys.argv[1]=='worker':worker(sys.argv[2])
 else:main()
