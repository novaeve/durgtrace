from pathlib import Path
import os,json,time,sys,subprocess,fcntl,shutil,collections,socket
from runtime import ROOT,dump
METHODS=['deepseek','codex'];WIDTH=4
def identity(pid):
 try:
  fields=Path(f'/proc/{pid}/stat').read_text().split(') ')[1].split()
  return fields[19] if fields[0]!='Z' else None
 except OSError:return None
def main():
 lock=(ROOT/'scheduler.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert json.loads((ROOT/'preflight/result.json').read_text())['passed']
 ids=[t['id'] for t in json.loads((ROOT/'public_tasks.json').read_text())]
 active={m:{} for m in METHODS};blocked={m:{} for m in METHODS};pilot={m:False for m in METHODS}
 previous=json.loads((ROOT/'scheduler_status.json').read_text()) if (ROOT/'scheduler_status.json').exists() else {}
 for method in METHODS:
  for it in previous.get('active',{}).get(method,[]):
   if identity(it['pid'])==it['identity']:active[method][it['task']]=it
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:args=(proc/'cmdline').read_bytes().decode().split(chr(0))
  except (OSError,UnicodeError):continue
  if str(ROOT/'worker.py') not in args:continue
  pos=args.index(str(ROOT/'worker.py'));m,tid=args[pos+1:pos+3]
  token=identity(int(proc.name))
  if m in METHODS and token:active[m][tid]={'task':tid,'pid':int(proc.name),'identity':token}
 while True:
  ready=shutil.disk_usage(ROOT).free>=30*1024**3;counts={}
  for method in METHODS:
   for tid,it in list(active[method].items()):
    if identity(it['pid'])==it['identity']:continue
    if not (ROOT/'runs'/method/tid/'record.json').exists():blocked[method][tid]='interrupted worker; retained partial outputs'
    del active[method][tid]
   pilot_record=ROOT/'runs'/method/ids[0]/'record.json'
   if pilot_record.exists():
    d=json.loads(pilot_record.read_text());pilot[method]=d['evaluation'] in ['passed','failed'] and d['agent'] in ['submitted','complete']
    if not pilot[method]:blocked[method][ids[0]]='pilot failed infrastructure or produced no submitted molecule'
   for tid in ids if pilot[method] else ids[:1]:
    if not ready or len(active[method])>=WIDTH:break
    out=ROOT/'runs'/method/tid
    if (out/'record.json').exists() or tid in active[method] or tid in blocked[method]:continue
    if (out/'workspace').exists():blocked[method][tid]='unclaimed partial output; not replayed';continue
    out.mkdir(parents=True,exist_ok=True)
    with (out/'scheduler_launch.log').open('a') as log:
     proc=subprocess.Popen([sys.executable,str(ROOT/'worker.py'),method,tid],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
    active[method][tid]={'task':tid,'pid':proc.pid,'identity':identity(proc.pid),'started':time.time()};print('START',method,tid,proc.pid,flush=True)
   records=[json.loads(p.read_text()) for p in (ROOT/'runs'/method).glob('*/record.json')]
   counts[method]={'total':340,'completed':len(records),'evaluation':dict(collections.Counter(d['evaluation'] for d in records)),'agent':dict(collections.Counter(d['agent'] for d in records)),'active':len(active[method]),'waiting':340-len(records)-len(active[method]),'pilot_passed':pilot[method]}
  report={'pid':os.getpid(),'updated':time.time(),'state':'running' if ready else 'waiting_disk','concurrency_per_method':WIDTH,'gpu_pool':[1,3,4,6],'active':{m:list(v.values()) for m,v in active.items()},'blocked':blocked,'counts':counts}
  if all(d['completed']==340 for d in counts.values()):report['state']='complete'
  if not any(active.values()) and any(blocked.values()):report['state']='needs_attention'
  dump(ROOT/'scheduler_status.json',report)
  if report['state'] in ['complete','needs_attention']:break
  time.sleep(5)
if __name__=='__main__':main()
