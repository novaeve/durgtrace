"""Durable six-worker Type4 queue; interrupted attempts require inspection."""
from pathlib import Path
import fcntl,json,os,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
def dump(path,data):
 p=Path(path);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(p)
def main():
 lock=(ROOT/'scheduler.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if not (ROOT/'private/model.env').exists():raise RuntimeError('Model authentication has not been provisioned')
 if not (ROOT/'preflight.ok').exists():raise RuntimeError('Preflight has not passed')
 ids=(ROOT/'task_list.txt').read_text().split();assert len(ids)==340 and len(set(ids))==340
 (ROOT/'worker_logs').mkdir(exist_ok=True);(ROOT/'worker_state').mkdir(exist_ok=True)
 active={};pending=[];blocked=[]
 for i,tid in enumerate(ids):
  result=ROOT/'evaluation/molclaw'/tid/'result.json'
  if result.exists():continue
  if (ROOT/'worker_state'/f'{tid}.json').exists() or (ROOT/'runs/molclaw'/tid/'workspace').exists():blocked.append(tid)
  else:pending.append((i,tid))
 def shutdown(signum,frame):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,shutdown)
 try:
  while pending or active:
   for tid,(p,log) in list(active.items()):
    rc=p.poll()
    if rc is None:continue
    log.close();dump(ROOT/'worker_state'/f'{tid}.json',{'status':'finished' if rc==0 else 'infrastructure_error','exit_code':rc,'ended':time.time()})
    if rc:blocked.append(tid)
    del active[tid]
   enough_disk=os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize>50*1024**3
   while pending and len(active)<6 and enough_disk:
    i,tid=pending.pop(0);log=(ROOT/'worker_logs'/f'{tid}.log').open('a')
    dump(ROOT/'worker_state'/f'{tid}.json',{'status':'starting','time':time.time()})
    p=subprocess.Popen([sys.executable,str(ROOT/'run.py'),'--task',tid,'--index',str(i)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    active[tid]=(p,log);dump(ROOT/'worker_state'/f'{tid}.json',{'status':'running','pid':p.pid,'started':time.time()})
   scored=list((ROOT/'evaluation/molclaw').glob('*/result.json'))
   dump(ROOT/'status.json',{'expected':340,'evaluated':len(scored),'active':list(active),'waiting':len(pending),'blocked':blocked,'disk_ok':enough_disk,'time':time.time()})
   time.sleep(10)
 finally:
  for p,log in active.values():
   if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
   log.close()
if __name__=='__main__':main()
