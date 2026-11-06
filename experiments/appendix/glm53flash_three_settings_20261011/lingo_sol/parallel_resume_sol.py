"""Run untouched SoL cases while the interrupted original pool finishes its active cases."""
import collections,fcntl,hashlib,importlib.util,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD_SESSION='gpt6luna-sol-3settings-20261010'
OLD_PID=2528261
def dump(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2));tmp.replace(path)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def live(pid):
 try:
  args=(Path('/proc')/str(pid)/'cmdline').read_bytes()
  return b'run.py' in args and b'SoL-Pi' in args
 except FileNotFoundError:return False
def main():
 with (ROOT/'locks/parallel_resume.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  state=json.loads((ROOT/'concurrency_restart_state.json').read_text())
  plan=next(p for p in state['plans'] if p['method']=='SoL-Pi')
  if plan['phase']!='draining' or not live(OLD_PID):
   dump(ROOT/'parallel_resume_state.json',{'phase':'not_needed','time':time.time()});return
  assert (ROOT/'concurrency_restart_pending.json').exists()
  assert plan['old_pid']==OLD_PID
  subprocess.run(['tmux','set-option','-w','-t',OLD_SESSION,'remain-on-exit','on'],check=True)
  held=True
  try:
   sys.argv=[str(ROOT/'run.py'),'SoL-Pi']
   spec=importlib.util.spec_from_file_location('sol_parallel_resume',ROOT/'run.py')
   runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
   assert runner.WORKERS==12
   runner.validate();runner.initialize()
   pilot,full=runner.ordered();ordered=pilot+full
   started=[i for i,j in enumerate(ordered) if runner.native_dir(j).exists() or (runner.final_dir(j)/'result.json').exists()]
   frontier=max(started)
   held_keys=[(j['setting'],j['case']['id']) for j in ordered[:frontier+21] if not (runner.final_dir(j)/'result.json').exists()]
   selected=[j for j in ordered[frontier+21:] if not (runner.final_dir(j)/'result.json').exists()]
   assert selected
   assert not any(runner.native_dir(j).exists() for j in selected),'Untouched cases only'
   preserved={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'runs/SoL-Pi').glob('*/*/result.json')}
   jobs_sha=sha(ROOT/'jobs.json');common_sha=sha(ROOT/'common.py')
   dump(ROOT/'parallel_resume_plan.json',{'workers':12,'old_draining_pid':OLD_PID,'old_session_hold':True,'frontier_index':frontier,'deferred_prefix_cases':held_keys,'selected_count':len(selected),'selected_keys':[(j['setting'],j['case']['id']) for j in selected],'jobs_sha256':jobs_sha,'common_sha256':common_sha,'time':time.time()})
   dump(ROOT/'parallel_resume_state.json',{'phase':'running','workers':12,'selected':len(selected),'deferred_prefix_count':len(held_keys),'time':time.time()})
   dump(ROOT/'state/SoL-Pi.json',{'phase':'full','model':'glm-5.3-flash','workers':12,'mode':'parallel_resume_with_original_case_draining','old_draining_pid':OLD_PID,'time':time.time()})
   print('TWELVE_WORKERS_PROCESSING_UNTOUCHED_SUFFIX',len(selected),flush=True)
   report=runner.batch(selected)
   assert sha(ROOT/'jobs.json')==jobs_sha and sha(ROOT/'common.py')==common_sha
   assert all((ROOT/p).exists() and sha(ROOT/p)==h for p,h in preserved.items()),'Completed results must be preserved'
   dump(ROOT/'parallel_resume_state.json',{'phase':'suffix_complete','workers':12,'processed':report['processed'],'time':time.time(),'existing_results_preserved':len(preserved)})
  finally:
   subprocess.run(['tmux','set-option','-w','-t',OLD_SESSION,'remain-on-exit','off'],capture_output=True)
   result=subprocess.run(['tmux','list-panes','-t',OLD_SESSION,'-F','#{pane_dead}'],capture_output=True,text=True)
   if result.returncode==0 and result.stdout.strip()=='1':
    subprocess.run(['tmux','kill-session','-t',OLD_SESSION],check=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  dump(ROOT/'parallel_resume_state.json',{'phase':'failed','error':str(exc),'time':time.time()})
  (ROOT/'parallel_resume_error.log').write_text(traceback.format_exc());raise
