import concurrent.futures,fcntl,json,resource,time,traceback
import worker as w
R=w.ROOT;STAGE='provider_rejection_retry_1';IDS=['source_108_loose_013','source_106_loose_065']
def run(cid):
 with (R/'locks'/(cid+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  assert not (R/'raw_results'/(cid+'.json')).exists()
  w.run_case(w.CASES[cid],STAGE)
  src=R/'native/MolClaw'/STAGE/cid;dst=R/'native/MolClaw/full'/cid
  archive=R/'retry_archive/provider_rejection_retry_1'/cid
  assert (src/'prompt.txt').read_text()==(archive/'native/prompt.txt').read_text()
  row=json.loads((src/'result.json').read_text())
  row.update(user_requested_retry={'attempt':1,'reason':'Bailian DataInspectionFailed; user requested one retry with original settings','prior_archive':str(archive),'policy':'Retain both attempts; no change to prompt, model, provider, tools or evaluator'},execution_host='a100',finished=time.time())
  w.dump(src/'result.json',row);assert not dst.exists();src.rename(dst)
  w.collect_existing(cid)
  return {'id':cid,'status':row['status'],'error':row.get('error')}
def main():
 soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE);resource.setrlimit(resource.RLIMIT_NOFILE,(min(65536,hard),hard))
 with (R/'provider_retry.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  done=[];errors=[]
  with concurrent.futures.ThreadPoolExecutor(2) as pool:
   jobs={pool.submit(run,cid):cid for cid in IDS}
   while jobs:
    finished,_=concurrent.futures.wait(jobs,timeout=10,return_when=concurrent.futures.FIRST_COMPLETED)
    for f in finished:
     cid=jobs.pop(f)
     try:done.append(f.result())
     except Exception:errors.append({'id':cid,'traceback':traceback.format_exc()})
    w.dump(R/'provider_retry_status.json',{'time':time.time(),'phase':'running' if jobs else ('requires_review' if errors else 'complete'),'ids':IDS,'active':len(jobs),'results':done,'execution_errors':errors})
if __name__=='__main__':main()
