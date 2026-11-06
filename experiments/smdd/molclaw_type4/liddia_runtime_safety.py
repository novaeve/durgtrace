"""Runtime failures are observable tool results; disk exhaustion stops work."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import time


class ToolExecutionError(RuntimeError):
    pass


class ResourceUnavailable(RuntimeError):
    pass


def wait_for_gpu(preferred, status_path=None, interval=60):
    while True:
        try:
            gpu=select_gpu(preferred)
            if status_path:atomic_json(status_path,{'state':'ready','gpu':gpu,'time':time.time()})
            return gpu
        except ResourceUnavailable as exc:
            if status_path:atomic_json(status_path,{'state':'waiting_gpu','reason':str(exc),'time':time.time()})
            time.sleep(interval)


def require_disk(path, minimum_gib=5):
    free=shutil.disk_usage(path).free
    if free < minimum_gib*1024**3:
        raise ResourceUnavailable(f'Disk free {free/1024**3:.1f} GiB is below {minimum_gib} GiB: {path}')


def require_gpu(gpu, minimum_mib=28000):
    result=subprocess.run(['nvidia-smi','-i',str(gpu),'--query-gpu=memory.free',
                           '--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
    free=int(result.stdout.strip())
    if free < minimum_mib:
        raise ResourceUnavailable(f'GPU {gpu} free {free} MiB is below {minimum_mib} MiB; no inference started')


def select_gpu(preferred, minimum_mib=28000):
    fixed=os.environ.get('LIDDIA_FIXED_GPU')
    if fixed is not None:
        gpu=int(fixed)
        require_gpu(gpu,minimum_mib)
        return gpu
    result=subprocess.run(['nvidia-smi','--query-gpu=index,memory.free',
                           '--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
    candidates={int(row.split(',')[0]):int(row.split(',')[1]) for row in result.stdout.splitlines() if row.strip()}
    if candidates.get(preferred,0)>=minimum_mib:return preferred
    eligible=[gpu for gpu,free in candidates.items() if free>=minimum_mib]
    if not eligible:raise ResourceUnavailable('No GPU has at least '+str(minimum_mib)+' MiB free')
    return max(eligible,key=candidates.get)


def atomic_json(path, value):
    path=Path(path)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,default=str)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read_json_record(path):
    path=Path(path)
    if not path.exists():return None
    try:
        return json.loads(path.read_text())
    except (ValueError,UnicodeError) as exc:
        return {'status':'corrupt_record','path':str(path),'error':str(exc)}


from contextlib import contextmanager
import fcntl

@contextmanager
def pocket_gpu_lease(gpu):
    from smdd_backends import ROOT
    with (ROOT/f'boltz_gpu{gpu}.lock').open('w') as lock:
        # Pocket2Mol is small; shared leases permit one bounded Type4 Boltz.
        # Full LIDDIA Boltz still takes an exclusive lease on the same file.
        fcntl.flock(lock,fcntl.LOCK_SH if gpu in (4,6) else fcntl.LOCK_EX)
        while True:
            try:
                require_gpu(gpu)
                break
            except ResourceUnavailable:
                time.sleep(60)
        yield
