from pathlib import Path
import json,subprocess,os,concurrent.futures,fcntl,hashlib,time
r=Path('/data2/chenfuxin/smdd_rescore_20261004')
lock=(r/'driver.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
tasks=json.loads((r/'manifest.json').read_text())['tasks']
python='/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python'
def worker(gpu,items):
 for item in items:
  out=Path(item['output']);assert hashlib.sha256((out/'solution.smi').read_bytes()).hexdigest()==item['solution_sha256']
  if (out/'rescore_status.json').exists():continue
  print('START',item['method'],item['task'],'GPU',gpu,flush=True)
  with (out/'rescore.log').open('w') as log:
   p=subprocess.run([python,str(r/'source/evaluate_type4.py'),item['task'],str(out),'--gpu',str(gpu)],env=dict(os.environ,LIDDIA_FIXED_GPU=str(gpu)),stdout=log,stderr=subprocess.STDOUT)
  result=out/'evaluation/result.json'
  status={'exit':p.returncode,'time':time.time(),'evaluation':json.loads(result.read_text()).get('status') if result.exists() else 'missing'}
  (out/'rescore_status.json').write_text(json.dumps(status))
  print('DONE',item['method'],item['task'],status,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(worker,gpu,tasks[i::2]) for i,gpu in enumerate([1,6])]
 for f in futures:f.result()
(r/'complete.json').write_text(json.dumps({'completed':time.time(),'count':len(tasks)}))
