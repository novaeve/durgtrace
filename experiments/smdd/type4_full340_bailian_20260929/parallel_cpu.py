"""Two tasks per method; adopt in-flight tasks without replaying them."""
import fcntl
import json
import os
import shutil
import socket
from pathlib import Path
import subprocess
import sys
import time
import batch

BASE = Path(__file__).resolve().parent
METHODS = ('chatdrug', 'agentdrug')

def heartbeat():
    address=os.environ.get('NOTIFY_SOCKET')
    if not address:return
    if address.startswith('@'):address='\0'+address[1:]
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:
        sock.sendto(b'WATCHDOG=1',address)

def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().split(') ')[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None

def recover(ids):
    """Recover current workers, including launches between two status writes."""
    active={m:{} for m in METHODS}
    status_path=BASE/'parallel_status.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {}
    blocked=status.get('blocked',{m:{} for m in METHODS})
    plan=json.loads((BASE/'parallel_handoff.json').read_text())
    saved=status.get('active',plan['adopted'])
    for method in METHODS:
        for item in saved.get(method,[]):
            if item.get('identity') is not None and identity(item['pid'])==item['identity']:
                active[method][item['task']]=dict(item,adopted=True)
    # A launcher can die immediately after fork and before the next checkpoint.
    # Discover the actual --task processes before considering any fresh launch.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            args=(proc/'cmdline').read_bytes().decode().split(chr(0))
            token=identity(int(proc.name))
        except (OSError,UnicodeError):continue
        script=str(BASE/'batch.py')
        if script not in args or '--task' not in args or token is None:continue
        # Prefer timeout wrapper (when present), rather than its Python child.
        try:
            parent=int((proc/'stat').read_text().split(') ')[1].split()[1])
            parent_args=Path(f'/proc/{parent}/cmdline').read_bytes().decode().split(chr(0))
        except (OSError,UnicodeError):parent_args=[]
        if script in parent_args and '--task' in parent_args:continue
        method=args[args.index(script)+1];tid=args[args.index('--task')+1]
        if method not in METHODS or tid not in ids:continue
        item=active[method].get(tid)
        if item and item['pid']!=int(proc.name):raise RuntimeError('Duplicate live task: '+method+'/'+tid)
        active[method][tid]=dict(item or {},task=tid,index=ids.index(tid),pid=int(proc.name),identity=token,started=(item or {}).get('started',time.time()),adopted=True,gpu_pool=[0,5,7])
        blocked.setdefault(method,{}).pop(tid,None)
    return active,blocked

def main():
    locks=[]
    for method in METHODS:
        lock=(BASE/method/'batch.lock').open('a')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(lock)
    ids=(BASE/'tasks340.txt').read_text().splitlines()
    assert len(ids)==340 and len(set(ids))==340
    active,blocked=recover(ids)
    attempted={m:set() for m in METHODS}
    for method in METHODS:
        attempted[method].update(active[method])
        attempted[method].update(blocked[method])
        (BASE/method/'supervisor.pid').write_text(str(os.getpid()))
    while True:
        heartbeat()
        disk_ready=shutil.disk_usage(BASE).free>=10*1024**3
        for method in METHODS:
            root=BASE/method
            for tid,item in list(active[method].items()):
                proc=item.get('process')
                running=proc.poll() is None if proc else identity(item['pid'])==item['identity']
                if running:continue
                if not (root/'records'/f'{tid}.json').exists():
                    # Preserve partial generation for investigation; never replay it.
                    blocked[method][tid]='worker exited without a terminal record'
                if item.get('log'):item['log'].close()
                del active[method][tid]
            for index,tid in enumerate(ids):
                if not disk_ready:break
                if len(active[method])>=2:break
                if tid in attempted[method] or (root/'records'/f'{tid}.json').exists():continue
                if (root/'run'/tid).exists() or (root/'evaluator'/tid).exists():
                    blocked[method][tid]='unclaimed existing output; not replayed'
                    attempted[method].add(tid);continue
                gpu=7 if method=='chatdrug' else 0
                (root/'logs').mkdir(exist_ok=True)
                log=(root/'logs'/f'{tid}.log').open('a')
                env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
                proc=subprocess.Popen(['timeout','--signal=TERM','--kill-after=30s','43200s',sys.executable,str(BASE/'batch.py'),method,'--gpu',str(gpu),'--task',tid,'--index',str(index)],cwd=BASE,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                item=dict(task=tid,index=index,pid=proc.pid,identity=identity(proc.pid),started=time.time(),gpu_pool=[0,5,7],process=proc,log=log,adopted=False)
                active[method][tid]=item;attempted[method].add(tid)
                print('START',method,tid,proc.pid,flush=True)
            report=batch.summary(root,ids)
            current=[{k:v for k,v in item.items() if k not in ('process','log')} for item in active[method].values()]
            status=dict(method=method,pid=os.getpid(),concurrency=2,gpu_pool=[0,5,7],workers=current,blocked=blocked[method],updated=time.time())
            if current:status.update(task=current[0]['task'],index=current[0]['index'])
            batch.dump(root/'current.json',status)
            if report['completed']==340:
                (root/'experiment.exit').write_text('0' if not report['infrastructure_errors'] else '2')
                (root/'RESULTS.md').write_text(f"{method}: 340/340 terminal tasks; {report['passed']}/340 passed; {report['infrastructure_errors']} infrastructure errors.\n")
        batch.dump(BASE/'parallel_status.json',dict(pid=os.getpid(),updated=time.time(),state='running' if disk_ready else 'waiting_disk',gpu_pool=[0,5,7],concurrency_per_method=2,active={m:[{k:v for k,v in it.items() if k not in ('process','log')} for it in active[m].values()] for m in METHODS},blocked=blocked))
        if not any(active.values()) and disk_ready:
            finished=json.loads((BASE/'parallel_status.json').read_text())
            finished['state']='needs_attention' if any(blocked.values()) else 'complete'
            batch.dump(BASE/'parallel_status.json',finished)
            break
        time.sleep(5)

if __name__=='__main__':
    main()
