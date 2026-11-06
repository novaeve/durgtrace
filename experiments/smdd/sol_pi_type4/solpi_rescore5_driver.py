"""Re-evaluate five frozen SoL-Pi submissions using the official evaluator."""
from pathlib import Path
import collections,concurrent.futures,fcntl,hashlib,json,os,runpy,subprocess,sys,time,traceback
BASE=Path('/yimin/zlc/sol_pi_type4_20261004')
MOL=Path('/yimin/zlc/molclaw_type4_20261003')
BATCH=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import runtime
from gpu_slots import acquire
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
 Path(out).mkdir(parents=True,exist_ok=True)
 with acquire(Path(log_path).parent) as (gpu,fds):
  args=[str(runtime.BOLTZ),str(BATCH/'boltz_transport.py'),'predict',str(yaml_path),'--out_dir',str(out),'--cache',str(MOL/'boltz_cache'),'--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--seed',str(seed),'--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),PYTHONNOUSERSITE='1',LD_LIBRARY_PATH=str(runtime.ROOTFS/'opt/conda/lib'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
  runtime.dump(Path(log_path).parent/'boltz_provenance.json',{'argv':args,'gpu':gpu,'batch':str(BATCH),'seed':seed,'samples':samples,'transport_sha256':sha(BATCH/'boltz_transport.py')})
  with open(log_path,'w') as log:proc=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,pass_fds=fds)
  if proc.returncode or not list(Path(out).rglob('affinity_input.json')):raise RuntimeError('Boltz did not produce a usable affinity result; inspect preserved log')
  return proc.returncode
runtime.gpu_run=gpu_run
def worker(tid,manifest):
 state=BATCH/'workers'/f'{tid}.json'
 if state.exists() and json.loads(state.read_text()).get('published'):
  assert sha(BASE/'runs/solpi'/tid/'solution.smi')==manifest['tasks'][tid]['submission_sha256']
  return json.loads(state.read_text())['score_status']
 runtime.dump(state,{'task':tid,'status':'running','started':time.time()})
 out=BATCH/'runs/solpi'/tid;original=BASE/'runs/solpi'/tid
 try:
  assert sha(original/'solution.smi')==sha(out/'solution.smi')==manifest['tasks'][tid]['submission_sha256']
  result_path=out/'evaluation/result.json'
  if not result_path.exists():
   with (BATCH/'logs'/f'{tid}.log').open('a') as log:
    proc=subprocess.run([sys.executable,str(BATCH/'driver.py'),'score',tid,str(out)],stdout=log,stderr=subprocess.STDOUT)
   if proc.returncode or not result_path.exists():raise RuntimeError('Official evaluator did not produce a result')
  result=json.loads(result_path.read_text());score=result['status']
  if score not in ['passed','failed']:raise RuntimeError('Rescore remains errored; original result retained')
  assert sha(original/'record.json')==manifest['tasks'][tid]['record_sha256']
  assert sha(original/'evaluation/result.json')==manifest['tasks'][tid]['evaluation_sha256']
  assert sha(original/'solution.smi')==manifest['tasks'][tid]['submission_sha256']
  (original/'evaluation').rename(BATCH/'original_evaluation'/tid)
  try:(out/'evaluation').rename(original/'evaluation')
  except Exception:
   (BATCH/'original_evaluation'/tid).rename(original/'evaluation');raise
  record=json.loads((original/'record.json').read_text());record.update(evaluation=score,completed=time.time())
  runtime.dump(original/'record.json',record)
  runtime.dump(original/'rescore_provenance.json',{'batch':str(BATCH),'submission_sha256':sha(original/'solution.smi'),'old_evaluation':str(BATCH/'original_evaluation'/tid),'promoted':time.time()})
  runtime.dump(state,{'task':tid,'status':'finished','score_status':score,'published':True,'ended':time.time()})
  print('FINISHED',tid,score,flush=True)
  return score
 except Exception as exc:
  runtime.dump(state,{'task':tid,'status':'infrastructure_error','error':repr(exc),'traceback':traceback.format_exc(),'ended':time.time()})
  print('ERROR',tid,repr(exc),flush=True);return 'errored'
def snapshot(manifest):
 states={tid:json.loads((BATCH/'workers'/f'{tid}.json').read_text()) for tid in manifest['tasks'] if (BATCH/'workers'/f'{tid}.json').exists()}
 runtime.dump(BATCH/'status.json',{'time':time.time(),'total':len(manifest['tasks']),'states':states,'running':sum(d['status']=='running' for d in states.values()),'ended':sum(d['status']!='running' for d in states.values()),'waiting':len(manifest['tasks'])-len(states)})
def main():
 lock=(BATCH/'driver.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 manifest=json.loads((BATCH/'manifest.json').read_text());assert len(manifest['tasks'])==5
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(worker,tid,manifest) for tid in manifest['tasks']]
  while not all(f.done() for f in futures):snapshot(manifest);time.sleep(5)
  results=[f.result() for f in futures]
 snapshot(manifest)
 assert all(sha(BASE/'runs/solpi'/tid/'solution.smi')==d['submission_sha256'] for tid,d in manifest['tasks'].items())
 assert all(sha(BASE/p)==h for p,h in manifest['all_record_hashes'].items() if Path(p).parent.name not in manifest['tasks'])
 assert all(sha(BASE/p)==h for p,h in manifest['source_hashes'].items())
 status=json.loads((BASE/'scheduler_status.json').read_text());assert status['state']=='complete' and not status['active']['solpi']
 records=[json.loads(p.read_text()) for p in (BASE/'runs/solpi').glob('*/record.json')]
 status['counts']['solpi'].update(completed=len(records),evaluation=dict(collections.Counter(d['evaluation'] for d in records)))
 status.update(updated=time.time(),rescore_batch=str(BATCH));runtime.dump(BASE/'scheduler_status.json',status)
 runtime.dump(BATCH/'completion.json',{'time':time.time(),'results':dict(collections.Counter(results)),'submissions_unchanged':True,'nonselected_records_unchanged':True,'source_files_unchanged':True,'counts':status['counts']['solpi']})
 print('COMPLETE',json.dumps(status['counts']['solpi']),flush=True)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='score':
  sys.argv=[str(BASE/'evaluate.py'),sys.argv[2],sys.argv[3]];runpy.run_path(str(BASE/'evaluate.py'),run_name='__main__')
 else:main()
