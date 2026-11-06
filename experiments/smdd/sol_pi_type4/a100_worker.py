#!/usr/bin/env python3
"""Restricted, public-payload-only Boltz worker; no model API credentials."""
from pathlib import Path
import json,sys,os,subprocess,fcntl,time,re,base64,zipfile,io
ROOT=Path('/yimin/zlc/sol_pi_type4_20261004')
MOL=Path('/yimin/zlc/molclaw_type4_20261003')
def dump(p,d):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d));tmp.replace(p)
def available():
 data=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True)
 return {int(row.split(',')[0]):int(row.split(',')[1]) for row in data.splitlines()}
def try_acquire():
 own=ROOT/'gpu_locks';own.mkdir(exist_ok=True);shared=MOL/'gpu_locks'
 with (shared/'admission.lock').open('a') as gate:
  fcntl.flock(gate,fcntl.LOCK_EX)
  free=available()
  for gpu in sorted((0,1),key=lambda g:-free[g]):
   if free[gpu]<36000:continue
   stamp=shared/f'gpu{gpu}.last_start'
   if stamp.exists() and time.time()-float(stamp.read_text())<90:continue
   owned=(own/f'gpu{gpu}.sol.lock').open('a')
   try:fcntl.flock(owned,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:owned.close();continue
   for slot in range(2):
    f=(shared/f'gpu{gpu}.slot{slot}.lock').open('a')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:f.close();continue
    if available()[gpu]<36000:f.close();continue
    stamp.write_text(str(time.time()));return gpu,[owned,f]
   owned.close()
 return None,[]
def package(job):
 prediction=job/'out/boltz_results_input/predictions/input'
 affinity=json.loads((prediction/'affinity_input.json').read_text())
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
  for p in prediction.iterdir():
   if p.is_file() and p.suffix in ['.json','.cif']:archive.writestr(p.name,p.read_bytes())
 assert buffer.tell()<50*1024**2
 return {'status':'complete','affinity':affinity,'prediction_archive_b64':base64.b64encode(buffer.getvalue()).decode(),'gpu':json.loads((job/'started.json').read_text())['gpu']}
def main():
 req=json.loads(sys.stdin.read(20*1024**2));jobid=req.get('job_id','')
 if req.get('action')=='probe':print(json.dumps({'free_mib':available(),'status':'available_probe'}));return
 assert re.fullmatch('[a-f0-9]{32}',jobid)
 payload=req['payload'];assert payload.get('version')==1 and isinstance(payload.get('sequences'),list)
 for row in payload['sequences']:
  for entity in row.values():assert not any(k in entity for k in ['msa','ccd'])
 samples=int(req['samples']);seed=int(req['seed']);assert 1<=samples<=100 and seed==42
 job=ROOT/'jobs'/jobid;job.mkdir(parents=True,exist_ok=True)
 lock=(job/'job.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print(json.dumps({'status':'pending'}));return
 if (job/'done.json').exists():print((job/'done.json').read_text());return
 if (job/'started.json').exists():
  if (job/'out/boltz_results_input/predictions/input/affinity_input.json').exists():
   result=package(job);dump(job/'done.json',result);print(json.dumps(result));return
  for proc in Path('/proc').iterdir():
   try:
    if proc.name.isdigit() and str(job/'input.yaml').encode() in (proc/'cmdline').read_bytes():print(json.dumps({'status':'pending'}));return
   except OSError:pass
  print(json.dumps({'status':'error','error':'Interrupted prediction has no final affinity; preserved for investigation'}));return
 gpu,leases=try_acquire()
 if gpu is None:print(json.dumps({'status':'busy'}));return
 try:
  # YAML is generated as valid JSON, a YAML subset; no deserialization of executable objects.
  (job/'input.yaml').write_text(json.dumps(payload));dump(job/'request.json',req)
  args=[str(MOL/'rootfs/opt/conda/bin/python'),'-m','boltz.main','predict',str(job/'input.yaml'),'--out_dir',str(job/'out'),'--cache',str(MOL/'boltz_cache'),'--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--diffusion_samples_affinity',str(samples),'--seed',str(seed),'--max_parallel_samples','1']
  dump(job/'started.json',{'gpu':gpu,'pid':os.getpid(),'time':time.time(),'argv':args})
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),PYTHONNOUSERSITE='1',LD_LIBRARY_PATH=str(MOL/'rootfs/opt/conda/lib'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
  for key in ['http_proxy','https_proxy','all_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']:env.pop(key,None)
  with (job/'boltz.log').open('w') as log:
   p=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800,pass_fds=tuple(f.fileno() for f in [lock]+leases))
  result=package(job) if p.returncode==0 else {'status':'error','exit':p.returncode,'error':(job/'boltz.log').read_text(errors='replace')[-3000:]}
  dump(job/'done.json',result);print(json.dumps(result))
 finally:
  for f in leases:f.close()
if __name__=='__main__':
 try:main()
 except Exception as exc:print(json.dumps({'status':'error','error':type(exc).__name__+': '+str(exc)}))
