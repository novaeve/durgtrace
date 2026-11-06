"""Two process leases per A100, with serialized admission and memory guard."""
from pathlib import Path
from contextlib import contextmanager
import fcntl,json,os,subprocess,time
ROOT=Path(__file__).resolve().parent
ADMISSION_COOLDOWN=90
POLL_SECONDS=10

@contextmanager
def acquire(out,wait_seconds=10800):
 locks=ROOT/'gpu_locks';locks.mkdir(exist_ok=True)
 lease=None;selected=None;deadline=time.monotonic()+wait_seconds
 while lease is None:
  if time.monotonic()>deadline:raise TimeoutError('GPU admission wait exceeded 3 hours')
  with (locks/'admission.lock').open('a') as gate:
   fcntl.flock(gate,fcntl.LOCK_EX)
   rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True)
   free={int(r.split(',')[0]):int(r.split(',')[1]) for r in rows.strip().splitlines()}
   for gpu in sorted((0,1),key=lambda g:-free[g]):
    if free[gpu]<36000:continue
    # Admission cooldown lets the preceding process allocate its model first.
    stamp=locks/f'gpu{gpu}.last_start'
    if stamp.exists() and time.time()-float(stamp.read_text())<ADMISSION_COOLDOWN:continue
    for slot in range(2):
     f=(locks/f'gpu{gpu}.slot{slot}.lock').open('a')
     try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:f.close();continue
     lease=f;selected=gpu;stamp.write_text(str(time.time()));break
    if lease is not None:break
  if lease is None:
   out.mkdir(parents=True,exist_ok=True)
   (out/'resource_wait.json').write_text(json.dumps({'status':'waiting_for_gpu','time':time.time(),'free_mib':free}))
   time.sleep(POLL_SECONDS)
 try:
  (out/'resource_wait.json').unlink(missing_ok=True)
  yield selected
 finally:
  if lease is not None:fcntl.flock(lease,fcntl.LOCK_UN);lease.close()
