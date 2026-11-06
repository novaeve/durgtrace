from pathlib import Path
from contextlib import contextmanager
import fcntl,json,os,subprocess,time,shutil
ROOT=Path(__file__).resolve().parent
SHARED=Path('/data2/chenfuxin/liddia_smdd_type4_20260928')
OLDPOOL=Path('/data2/chenfuxin/smdd_type4_full340_bailian_20260929/gpu_leases')
POOL=(1,3,4,6)
def snapshot():
 rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],text=True,timeout=15)
 apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True,timeout=15)
 foreign=set()
 for row in apps.splitlines():
  uid,pid=[s.strip() for s in row.split(',')]
  try:
   proc=Path('/proc')/pid
   if proc.stat().st_uid!=os.getuid() or b'boltz.main' in (proc/'cmdline').read_bytes():foreign.add(uid)
  except OSError:foreign.add(uid)
 return {int(i):int(free) for row in rows.splitlines() for i,uid,free in [[s.strip() for s in row.split(',')]] if int(i) in POOL and uid not in foreign}
@contextmanager
def acquire(out,wait_seconds=21600):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 locks=ROOT/'gpu_locks';locks.mkdir(exist_ok=True)
 deadline=time.monotonic()+wait_seconds;lease=[];gpu=None
 while gpu is None:
  if time.monotonic()>deadline:raise TimeoutError('GPU admission exceeded six hours')
  if shutil.disk_usage(ROOT).free<30*1024**3:
   (out/'resource_wait.json').write_text(json.dumps({'state':'waiting_disk','time':time.time()}));time.sleep(15);continue
  with (locks/'admission.lock').open('a') as gate:
   fcntl.flock(gate,fcntl.LOCK_EX)
   free=snapshot()
   for candidate in sorted(free,key=lambda g:-free[g]):
    if free[candidate]<28000:continue
    files=[]
    try:
     for p in [locks/f'gpu{candidate}.lock',SHARED/f'boltz_gpu{candidate}.lock',OLDPOOL/f'gpu{candidate}.lock']:
      f=p.open('a');files.append(f);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     if snapshot().get(candidate,0)<28000:raise BlockingIOError()
     lease=files;gpu=candidate;break
    except BlockingIOError:
     for f in reversed(files):f.close()
  if gpu is None:
   (out/'resource_wait.json').write_text(json.dumps({'state':'waiting_gpu','pool':POOL,'free_mib':free,'time':time.time()}));time.sleep(5)
 try:
  (out/'resource_wait.json').unlink(missing_ok=True)
  yield gpu,[f.fileno() for f in lease]
 finally:
  for f in reversed(lease):f.close()
