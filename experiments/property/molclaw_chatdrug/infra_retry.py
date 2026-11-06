import concurrent.futures,fcntl,json,time,traceback,os
from pathlib import Path
import worker as w
R=w.ROOT;STAGE='infra_retry_connection_loss_1'
IDS=json.loads((R/'infra_retry_ids.json').read_text())
def run(cid):
 with (R/'locks'/(cid+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if (R/'raw_results'/(cid+'.json')).exists():return
  w.run_case(w.CASES[cid],STAGE)
  src=R/'native/MolClaw'/STAGE/cid;dst=R/'native/MolClaw/full'/cid
  row=json.loads((src/'result.json').read_text())
  row.update(infrastructure_retry=dict(attempt=1,cause='Shared proxy killed by cross-case pkill; terminal ECONNREFUSED',prior_archive=str(R/'infra_archive/confirmed_connection_loss_128'/cid)),execution_host='a100',finished=time.time())
  w.dump(src/'result.json',row)
  assert not dst.exists();src.rename(dst)
  w.collect_existing(cid)
def main():
 with (R/'infra_retry.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  pending=[i for i in IDS if not (R/'raw_results'/(i+'.json')).exists()];active={}
  with concurrent.futures.ThreadPoolExecutor(32) as pool:
   while pending or active:
    s=json.loads((R/'status.json').read_text());primary=max(0,s.get('active',0)-s.get('legacy_active',0))
    slots=min(32,max(0,128-primary))
    while pending and len(active)<slots:
     cid=pending.pop(0);active[pool.submit(run,cid)]=cid
    if active:
     done,_=concurrent.futures.wait(active,timeout=5,return_when=concurrent.futures.FIRST_COMPLETED)
     for f in done:f.result();active.pop(f)
    else:time.sleep(5)
    w.dump(R/'infra_retry_status.json',dict(time=time.time(),expected=len(IDS),processed=sum((R/'raw_results'/(i+'.json')).exists() for i in IDS),active=len(active),queued=len(pending),phase='running' if pending or active else 'complete'))
if __name__=='__main__':
 try:main()
 except Exception:w.dump(R/'infra_retry_error.json',dict(time=time.time(),traceback=traceback.format_exc()));raise
