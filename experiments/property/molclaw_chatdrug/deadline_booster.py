"""Disjoint pending-case scheduling, reserving actual live external episodes only."""
import collections,concurrent.futures,fcntl,json,os,time,traceback,urllib.request
from pathlib import Path
import worker as w
R=w.ROOT

def live_cases():
 cases=set()
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if (p/'comm').read_text().strip()!='claude':continue
   cwd=(p/'cwd').resolve()
   if str(cwd).startswith(str(R/'native/MolClaw')+'/'):cases.add(cwd.name)
  except OSError:pass
 return cases

def main():
 with (R/'deadline_booster.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ids=json.loads((R/'deadline_booster_ids.json').read_text())
  pending=collections.deque(i for i in ids if not (R/'raw_results'/(i+'.json')).exists());active={}
  cfg=json.loads((R/'deadline_control.json').read_text());limit=cfg['initial_total'];lastscale=time.time();lastbad=0;laststatus=0;failures=[]
  proxylog=R/'proxy.log';pos=proxylog.stat().st_size
  with concurrent.futures.ThreadPoolExecutor(cfg['maximum_total']) as pool:
   while pending or active:
    cfg=json.loads((R/'deadline_control.json').read_text());now=time.time()
    live=live_cases();owned=set(active.values());external=len(live-owned)
    with proxylog.open('rb') as f:f.seek(pos);tail=f.read().decode(errors='replace');pos=f.tell()
    errors=sum(tail.count(s) for s in ['429 Too Many Requests','502 Bad Gateway','503 Service Unavailable','504 Gateway Timeout','APIConnectionError'])
    available=next(int(l.split()[1])/1048576 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));load=os.getloadavg()[0]
    pressure=available<cfg['min_memory_gib'] or load>cfg['max_load']
    if errors or pressure:lastbad=now
    if (errors>=3 or pressure) and now-lastscale>60:limit=max(128,limit-64);lastscale=now
    elif not errors and not pressure and now-lastbad>120 and now-lastscale>120:limit=min(cfg['maximum_total'],limit+64);lastscale=now
    healthy=False
    try:healthy=urllib.request.urlopen('http://127.0.0.1:49493/health/liveliness',timeout=3).status==200
    except Exception:pass
    while pending and len(active)<max(0,limit-external-4) and healthy and not (R/'pause_deadline.request').exists():
     cid=pending.popleft();active[pool.submit(w.execute,cid)]=cid
    if active:
     done,_=concurrent.futures.wait(active,timeout=5,return_when=concurrent.futures.FIRST_COMPLETED)
     for f in done:
      cid=active.pop(f)
      try:f.result()
      except Exception:failures.append({'id':cid,'time':time.time(),'traceback':traceback.format_exc()})
    else:time.sleep(5)
    if now-laststatus>15:
     laststatus=now
     w.dump(R/'deadline_booster_status.json',dict(time=time.time(),phase='running',assigned=len(ids),processed=sum((R/'raw_results'/(i+'.json')).exists() for i in ids),active=len(active),external_native=external,actual_native=len(live),queued=len(pending),total_limit=limit,recent_api_errors=errors,resource_pressure=pressure,available_memory_gib=available,load=load,proxy_ok=healthy,execution_exceptions=failures))
  w.dump(R/'deadline_booster_status.json',dict(time=time.time(),phase='complete' if not failures else 'requires_review',assigned=len(ids),processed=sum((R/'raw_results'/(i+'.json')).exists() for i in ids),active=0,queued=0,execution_exceptions=failures))
  # Restore the original queue after our pending partition has finished; each
  # case lock plus existing-result check skips already completed episodes.
  if not failures:(R/'pause_generation.request').unlink(missing_ok=True)
if __name__=='__main__':
 try:main()
 except Exception:w.dump(R/'deadline_booster_error.json',dict(time=time.time(),traceback=traceback.format_exc()));raise
