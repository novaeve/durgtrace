"""Recover native client transport timeouts after the active primary pipeline exits."""
import collections,concurrent.futures,fcntl,hashlib,importlib.util,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SESSION='gpt6luna-sol-3settings-20261010'
def dump(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(p)
def live():
 if (ROOT/'concurrency_restart_pending.json').exists():return True
 return subprocess.run(['tmux','has-session','-t',SESSION],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def eligible(row):
 return row.get('status')=='error' and any(s in str(row.get('error','')) for s in ('Request timed out.','APITimeoutError','APIConnectionError'))
def rows():
 return [json.loads(p.read_text()) for p in (ROOT/'runs/SoL-Pi').glob('*/*/result.json')]
def main():
 lockpath=ROOT/'locks/transport_timeout_recovery.lock';lockpath.parent.mkdir(exist_ok=True)
 with lockpath.open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while live():
   queued=[{'setting':r['setting'],'id':r['id'],'error':r.get('error')} for r in rows() if eligible(r)]
   dump(ROOT/'transport_recovery_state.json',{'phase':'queued_until_primary_exits','queued':queued,'count':len(queued),'time':time.time(),
     'policy':'SDK request timeout is infrastructure; native wall/idle budget timeouts and model length finishes remain terminal. No correctness-selected retries.'})
   time.sleep(30)
  sys.argv=[str(ROOT/'run.py'),'SoL-Pi']
  spec=importlib.util.spec_from_file_location('timeout_recovery_native',ROOT/'run.py')
  runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
  runner.validate();runner.initialize()
  runner.MARKERS=runner.MARKERS+('Request timed out.','APITimeoutError','APIConnectionError')
  bykey={(j['setting'],j['case']['id']):j for j in runner.JOBS}
  recovered=[]
  for sweep in range(3):
   pending=[]
   for row in rows():
    if eligible(row) or (row.get('status')=='error' and runner.infrastructure(bykey[(row['setting'],row['id'])],row)):
     job=bykey[(row['setting'],row['id'])]
     archive=runner.archive(job,'sdk_transport_'+str(sweep))
     recovered.append({'setting':row['setting'],'id':row['id'],'reason':row.get('error'),'archive':archive})
     pending.append(job)
   if not pending:break
   dump(ROOT/'transport_recovery_state.json',{'phase':'recovering','sweep':sweep+1,'pending':len(pending),'recovered_episodes':recovered,'time':time.time()})
   runner.batch(pending)
  rr=rows();errors=[r for r in rr if r.get('status')=='error']
  report=runner.summary()
  assert report['processed']==4200
  state=json.loads((ROOT/'state/SoL-Pi.json').read_text())
  state.update(phase='attention_required' if errors else 'complete',processed=4200,expected=4200,error_count=len(errors),time=time.time(),transport_timeout_recovery=True)
  dump(ROOT/'state/SoL-Pi.json',state)
  dump(ROOT/'transport_recovery_state.json',{'phase':'attention_required' if errors else 'complete','processed':4200,
   'recovered_episodes':recovered,'error_count':len(errors),'time':time.time()})
if __name__=='__main__':
 os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
 try:main()
 except Exception as exc:
  dump(ROOT/'transport_recovery_state.json',{'phase':'failed','error':str(exc),'time':time.time()})
  (ROOT/'transport_recovery_error.log').write_text(traceback.format_exc());raise
