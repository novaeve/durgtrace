from pathlib import Path
from contextlib import contextmanager
import fcntl,json,subprocess,time,shutil
ROOT=Path(__file__).resolve().parent
MOL=Path('/yimin/zlc/molclaw_type4_20261003')
@contextmanager
def acquire(out,wait_seconds=21600):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 shared=MOL/'gpu_locks'
 deadline=time.monotonic()+wait_seconds;leases=[];selected=None
 while selected is None:
  if time.monotonic()>deadline:raise TimeoutError('GPU queue exceeded six hours')
  if shutil.disk_usage(ROOT).free<50*1024**3:
   (out/'resource_wait.json').write_text(json.dumps({'status':'waiting_disk','time':time.time()}));time.sleep(15);continue
  with (shared/'admission.lock').open('a') as gate:
   fcntl.flock(gate,fcntl.LOCK_EX)
   rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True)
   free={int(row.split(',')[0]):int(row.split(',')[1]) for row in rows.splitlines()}
   for gpu in sorted((0,1),key=lambda g:-free[g]):
    if free[gpu]<36000:continue
    stamp=shared/f'gpu{gpu}.last_start'
    if stamp.exists() and time.time()-float(stamp.read_text())<90:continue
    # Shared slots include leases held by workers launched before this update.
    # Two slots per GPU let SoL use the capacity released by MolClaw.
    for slot in range(2):
     f=(shared/f'gpu{gpu}.slot{slot}.lock').open('a')
     try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:f.close();continue
     memory=int(subprocess.check_output(['nvidia-smi','-i',str(gpu),'--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
     if memory<36000:f.close();continue
     leases=[f];selected=gpu;stamp.write_text(str(time.time()));break
    if selected is not None:break
  if selected is None:
   (out/'resource_wait.json').write_text(json.dumps({'status':'waiting_gpu','free_mib':free,'shared_molclaw_slots':True,'time':time.time()}));time.sleep(10)
 try:
  (out/'resource_wait.json').unlink(missing_ok=True)
  yield selected,[f.fileno() for f in leases]
 finally:
  for f in reversed(leases):f.close()
