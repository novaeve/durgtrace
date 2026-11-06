"""Exclusive Boltz leases on the three GPUs reserved for CPU-hosted Type4."""
import argparse
import fcntl
import json
import os
import shutil
from pathlib import Path
import subprocess
import time

ROOT = Path('/data2/chenfuxin/smdd_type4_full340_bailian_20260929')
POOL = (0, 5, 7)
BORROW = (4, 6)
LIDDIA = Path('/data2/chenfuxin/liddia_smdd_type4_20260928')
POCKET_SCRIPT = str(LIDDIA/'runs/full_type4_parallel3/source/pocket_runtime.py')

def is_own_pocket(pid):
    try:
        proc=Path('/proc')/str(pid)
        return proc.stat().st_uid==os.getuid() and POCKET_SCRIPT in (proc/'cmdline').read_bytes().decode().split(chr(0))
    except (OSError,UnicodeError):
        return False

def small_job(job):
    # Admit short, single-protein jobs only. Large complexes retain exclusive GPUs.
    try:
        import yaml
        data=yaml.safe_load((job/'input.yaml').read_text())
        seqs=data['sequences']
        proteins=[s['protein'] for s in seqs if 'protein' in s]
        return len(proteins)==1 and isinstance(proteins[0]['id'],str) and 0<len(proteins[0]['sequence'])<=400 and len(seqs)==2 and any('ligand' in s and len(s['ligand'].get('smiles',''))<=300 for s in seqs)
    except (ImportError,KeyError,TypeError,ValueError):
        return False

class Lease:
    def __init__(self,files):self.files=files
    def fileno(self):return self.files[0].fileno()
    def descriptors(self):return tuple(f.fileno() for f in self.files)
    def close(self):
        for f in reversed(self.files):f.close()

def snapshot():
    data = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.used,utilization.gpu', '--format=csv,noheader,nounits'], text=True, timeout=15)
    apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader'], text=True, timeout=15)
    occupants={}
    for line in apps.splitlines():
        uid,pid=[x.strip() for x in line.split(',')]
        occupants.setdefault(uid,[]).append(int(pid))
    result = []
    for line in data.splitlines():
        idx, uid, used, util = [x.strip() for x in line.split(',')]
        if int(idx) in POOL and uid not in occupants and int(used) < 512 and int(util) < 10:
            result.append(int(idx))
        if int(idx) in BORROW and 0<int(used)<2048 and int(util)<35 and occupants.get(uid) and all(is_own_pocket(p) for p in occupants[uid]):
            result.append(int(idx))
    return sorted(result,key=lambda gpu:(gpu in BORROW,gpu))

def acquire(timeout=5400,allow_borrow=False):
    (ROOT/'gpu_leases').mkdir(exist_ok=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if shutil.disk_usage(ROOT).free < 20*1024**3:
            time.sleep(15);continue
        for gpu in snapshot():
            if gpu in BORROW and not allow_borrow:continue
            lock = (ROOT/'gpu_leases'/f'gpu{gpu}.lock').open('a+')
            files=[lock]
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if gpu in BORROW:
                    shared=(LIDDIA/f'boltz_gpu{gpu}.lock').open('a+')
                    files.append(shared)
                    fcntl.flock(shared,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError:
                Lease(files).close(); continue
            if gpu in snapshot():
                return gpu, Lease(files)
            Lease(files).close()
        time.sleep(3)
    raise TimeoutError('No reserved GPU became available within 90 minutes')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('job'); p.add_argument('--samples', type=int, default=10); p.add_argument('--seed', type=int, default=42)
    a = p.parse_args()
    job = Path(a.job).resolve()
    assert job.parent == Path('/data2/chenfuxin/smdd_boltz_jobs')
    assert (job/'input.yaml').is_file()
    job_lock=(job/'execution.lock').open('a+')
    # The same remote job may be reconnected after SSH transport failure.
    # Serialize reconnects and never run a second scientific computation.
    deadline=time.monotonic()+7300
    while True:
        try:
            fcntl.flock(job_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
        except BlockingIOError:
            if time.monotonic()>deadline:raise TimeoutError('Existing job is still running')
            time.sleep(3)
    lease_path=job/'gpu_lease.json'
    if lease_path.exists():
        previous=json.loads(lease_path.read_text())
        if 'returncode' in previous:raise SystemExit(previous['returncode'])
        result=job/'out/boltz_results_input/predictions/input/affinity_input.json'
        if result.exists():
            json.loads(result.read_text())
            previous.update(finished=time.time(),returncode=0,recovered_after_disconnect=True)
            lease_path.write_text(json.dumps(previous,indent=2));raise SystemExit(0)
        raise RuntimeError('Interrupted existing job without final affinity; refusing replay')
    requested = time.time()
    gpu, lock = acquire(allow_borrow=small_job(job))
    lease = dict(gpu=gpu, pool=list(POOL), borrowed=gpu in BORROW, memory_fraction=0.78 if gpu in BORROW else None, pid=os.getpid(), requested=requested, started=time.time(), job=str(job))
    (job/'gpu_lease.json').write_text(json.dumps(lease, indent=2))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), PYTHONPATH=str(ROOT/'boltz_deps'))
    cmd = ['timeout', '--signal=TERM', '--kill-after=30s', '1800s', '/data2/chenfuxin/.local/bin/boltz', 'predict', str(job/'input.yaml'), '--out_dir', str(job/'out'), '--cache', '/data2/chenfuxin/boltz-cache', '--use_msa_server', '--use_potentials', '--accelerator', 'gpu', '--devices', '1', '--diffusion_samples', str(a.samples), '--diffusion_samples_affinity', str(a.samples), '--seed', str(a.seed), '--max_parallel_samples', '2']
    if gpu in BORROW:
        code="import torch,runpy,sys;torch.cuda.set_per_process_memory_fraction(0.78,0);script=sys.argv.pop(1);sys.argv[0]=script;runpy.run_path(script,run_name='__main__')"
        cmd[4:4]=['/usr/bin/python3','-c',code]
    with (job/'boltz.log').open('w') as log:
        # The computation inherits the lock, so even loss of the SSH wrapper
        # cannot prematurely make the GPU available to another pool job.
        result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, pass_fds=lock.descriptors()+(job_lock.fileno(),))
    lease.update(finished=time.time(), returncode=result.returncode)
    (job/'gpu_lease.json').write_text(json.dumps(lease, indent=2))
    lock.close()
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
