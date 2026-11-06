import concurrent.futures,fcntl,json,time,traceback
import worker as w
R=w.ROOT
def main():
 with (R/'cpu_transfer.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ids=json.loads((R/'cpu_transfer_ids.json').read_text());todo=[cid for cid in ids if not (R/'raw_results'/(cid+'.json')).exists()];errors=[]
  with concurrent.futures.ThreadPoolExecutor(16) as pool:
   jobs={pool.submit(w.execute,cid):cid for cid in todo}
   while jobs:
    done,_=concurrent.futures.wait(jobs,timeout=15,return_when=concurrent.futures.FIRST_COMPLETED)
    for f in done:
     cid=jobs.pop(f)
     try:f.result()
     except Exception:errors.append(dict(id=cid,traceback=traceback.format_exc()))
    w.dump(R/'cpu_transfer_status.json',dict(time=time.time(),phase='running' if jobs else ('requires_review' if errors else 'complete'),assigned=len(ids),processed=sum((R/'raw_results'/(cid+'.json')).exists() for cid in ids),remaining=len(jobs),errors=errors))
if __name__=='__main__':main()
