"""Independent watcher for the two unfinished experiment lanes."""
import fcntl,json,os,subprocess,time,traceback,urllib.request
from pathlib import Path
from resilience_common import read,write,alive,repair_idle_codex,repair_idle_direct,permanent_driver_error
ROOT=Path(__file__).resolve().parent;PY='/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python'
assert ROOT==Path('/data/chenfuxin/glm53flash_three_settings_20261011')

def tick():
 report={'pid':os.getpid(),'time':time.time(),'repairs':{},'blocked':{}}
 if read(ROOT/'run_control.json',{}).get('paused_by_user') or (ROOT/'maintenance.json').exists():
  report['phase']='manual_pause';write(ROOT/'resilience_gpu_state.json',report);return
 try:
  with urllib.request.urlopen('http://127.0.0.1:18853/health',timeout=5) as r:health=json.load(r)
 except Exception as e:
  report.update(phase='waiting_gateway',reason=type(e).__name__);write(ROOT/'resilience_gpu_state.json',report);return
 hold=read(ROOT/'provider_hold.json')
 if health.get('halted'):
  report.update(phase='waiting_provider',reason=health['halted']);write(ROOT/'resilience_gpu_state.json',report);return
 if hold:
  auto=hold.get('hold_type')=='provider_auto' or str(hold.get('reason','')).startswith(('Selected GLM provider halted','Official BigModel error 1113'))
  if not auto:
   report['phase']='manual_maintenance';write(ROOT/'resilience_gpu_state.json',report);return
  target=ROOT/'auto_recovery'/('provider_hold_'+str(time.time_ns())+'.json')
  target.parent.mkdir(parents=True,exist_ok=True);(ROOT/'provider_hold.json').rename(target)
  report['provider_auto_resumed']=True
  for statepath in (ROOT/'codex/state.json',ROOT/'direct/uncapped_retry1120/state.json'):
   previous=read(statepath,{})
   if previous.get('phase')=='awaiting_quota':
    previous.update(phase='full',time=time.time());previous.pop('reason',None);write(statepath,previous)
 restarts=read(ROOT/'resilience_restart_state.json',{})
 for name,folder,script,expected,repair in [
  ('Codex','codex','run_benchmark.py',4200,repair_idle_codex),
  ('GLM_direct_retry1120','direct/uncapped_retry1120','run_retry.py',1120,repair_idle_direct)]:
  method=ROOT/folder;state=read(method/'state.json',{})
  if not method.exists():continue
  if name=='Codex' and alive(ROOT/'parallel_codex_recovery.py'):
   report['parallel_recovery_active']=True;continue
  if alive(method/script) or alive(ROOT/'supervisor.py',name):continue
  rows=[read(p) for p in (method/'runs'/('Codex' if name=='Codex' else 'GLM_direct')).glob('*/*/result.json')]
  rows=[r for r in rows if r is not None]
  from resilience_common import recoverable
  pending_infra=any(recoverable(r) for r in rows)
  if len(rows)==expected and not pending_infra:
   state.update(phase='complete',processed=expected,expected=expected,time=time.time());state.pop('reason',None);write(method/'state.json',state);continue
  if permanent_driver_error(state):report['blocked'][name]=state.get('error');continue
  prior=restarts.get(name,{})
  if prior.get('processed')!=len(rows):prior={}
  delay=min(300,30*2**min(prior.get('attempts',0),4))
  if time.time()-prior.get('last_restart',0)<delay:continue
  trace=method/'pipeline_error.log'
  if state.get('phase')=='failed' and trace.exists() and 'AssertionError' in trace.read_text()[-2000:]:
   report['blocked'][name]='Pinned-code/scoring assertion needs review';continue
  # Stop only orphaned native children of this lane before moving unfinished attempt directories.
  if name=='Codex':
   cmd=[PY,str(ROOT/'cleanup_idle_codex.py')]
   subprocess.run(cmd,check=True,timeout=30,stdout=subprocess.DEVNULL)
  repaired=repair(ROOT);report['repairs'][name]=len(repaired)
  state.update(phase='resuming',time=time.time());state.pop('reason',None);state.pop('errors',None);state.pop('error',None)
  write(method/'state.json',state)
  restarts[name]={'processed':len(rows),'attempts':prior.get('attempts',0)+1,'last_restart':time.time()}
 write(ROOT/'resilience_restart_state.json',restarts)
 subprocess.run([PY,str(ROOT/'gpu_doctor.py')],check=True,timeout=30,stdout=subprocess.DEVNULL)
 report['phase']='watching';write(ROOT/'resilience_gpu_state.json',report)

if __name__=='__main__':
 with (ROOT/'resilience_gpu.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while True:
   try:tick()
   except Exception:
    with (ROOT/'resilience_gpu_errors.log').open('a') as f:f.write(str(time.time())+'\n'+traceback.format_exc()+'\n')
   time.sleep(30)
