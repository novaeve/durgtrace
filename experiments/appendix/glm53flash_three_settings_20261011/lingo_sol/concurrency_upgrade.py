"""Drain existing worker pools, then resume the same jobs with higher concurrency."""
import ast,fcntl,hashlib,json,os,shlex,signal,subprocess,sys,time,traceback
from pathlib import Path
BASE=Path('/data2/chenfuxin')
ROOT=BASE/'gpt6luna_lingo_sol_three_settings_20261010'
PY=BASE/'chatdrug_generalization_20260920/venv/bin/python'
PLANS=[
 {'method':'SoL-Pi','root':ROOT,'session':'gpt6luna-sol-3settings-20261010','workers':12,'log':'SoL-Pi_pipeline.log'},
 {'method':'MolClaw','root':BASE/'gpt6luna_molclaw_three_settings_20261010','session':'gpt6luna-molclaw-3settings-20261010','workers':16,'log':'pipeline.log'}]
STATE=ROOT/'concurrency_restart_state.json'
RECOVERY='gpt6luna-sol-infra-recovery-20261010'
def dump(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2));tmp.replace(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def alive(session):
 return subprocess.run(['tmux','has-session','-t',session],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def processes(plan):
 found=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   args=[a.decode(errors='replace') for a in (p/'cmdline').read_bytes().split(b'\0') if a]
   if not any(Path(a).name=='run.py' for a in args) or (p/'cwd').resolve()!=plan['root']:continue
   if plan['method']=='SoL-Pi' and 'SoL-Pi' not in args:continue
   status=dict(line.split(':',1) for line in (p/'status').read_text().splitlines() if ':' in line)
   found.append((int(p.name),status))
  except (FileNotFoundError,PermissionError,ProcessLookupError):pass
 return found
def same_process(plan):
 return any(pid==plan['old_pid'] for pid,_ in processes(plan))
def launch(session,root,args,log,workers):
 assert not alive(session),session
 command='cd '+shlex.quote(str(root))+' && umask 077 && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MOL_BENCH_WORKERS='+str(workers)+' '+shlex.join([str(PY),'-u',*args])+' >> '+shlex.quote(log)+' 2>&1'
 subprocess.run(['tmux','new-session','-d','-s',session,command],check=True)
def selftest(revision):
 marker=revision/'signal_test_finished.txt'
 code="import concurrent.futures,time,pathlib\nwith concurrent.futures.ThreadPoolExecutor(1) as pool:\n f=pool.submit(lambda:(time.sleep(1),pathlib.Path("+repr(str(marker))+").write_text('finished')))\n print('READY',flush=True)\n concurrent.futures.wait([f])\n"
 proc=subprocess.Popen([str(PY),'-u','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 assert proc.stdout.readline().strip()=='READY'
 os.kill(proc.pid,signal.SIGINT);proc.communicate(timeout=15)
 assert proc.returncode!=0 and marker.read_text()=='finished','Active worker must finish after parent-only SIGINT'
 dump(revision/'signal_test.json',{'passed':True,'worker_finished_after_parent_sigint':True})
def main():
 with (ROOT/'concurrency_restart.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  rev=ROOT/'execution_revisions'/('parallelism_'+time.strftime('%Y%m%dT%H%M%S'))
  rev.mkdir(parents=True);selftest(rev)
  plans=[]
  for p in PLANS:
   p=dict(p);r=p['root'];found=processes(p)
   assert len(found)==1,(p['method'],found)
   pid,status=found[0]
   assert not (int(status['SigIgn'].strip(),16)&2),'Parent ignores SIGINT'
   assert int(status['SigCgt'].strip(),16)&2,'Parent must handle SIGINT'
   p['old_pid']=pid;p['phase']='prepared'
   p['preserved']={str(f.relative_to(r)):sha(f) for f in (r/'runs'/p['method']).glob('*/*/result.json')}
   p['jobs_sha256']=sha(r/'jobs.json');p['common_sha256']=sha(r/'common.py')
   text=(r/'run.py').read_text()
   assert text.count('WORKERS=4')==1
   changed=text.replace('WORKERS=4',"WORKERS=int(os.environ.get('MOL_BENCH_WORKERS', '"+str(p['workers'])+"'))",1)
   ast.parse(changed);p['old_code']=text;p['new_code']=changed
   plans.append(p)
  recovery_path=ROOT/'infra_timeout_recovery.py'
  recovery_text=recovery_path.read_text()
  assert "def live():\n return subprocess.run(" in recovery_text
  recovery_new=recovery_text.replace("def live():\n return subprocess.run(","def live():\n if (ROOT/'concurrency_restart_pending.json').exists():return True\n return subprocess.run(",1)
  ast.parse(recovery_new)
  rs=json.loads((ROOT/'transport_recovery_state.json').read_text())
  assert rs['phase']=='queued_until_primary_exits',rs['phase']
  dump(ROOT/'concurrency_restart_pending.json',{'reason':'Authorized concurrency increase; primary pools drain before restart','time':time.time()})
  for p in plans:
   r=p['root'];d=rev/p['method'];d.mkdir()
   (d/'run.before.py').write_text(p['old_code'])
   (r/'run.py').write_text(p['new_code'])
   dump(d/'preserved_results.json',p['preserved'])
   dump(r/'concurrency_config.json',{'workers':p['workers'],'previous_workers':4,'revision':str(rev),'time':time.time(),'jobs_sha256':p['jobs_sha256'],'common_sha256':p['common_sha256']})
  (rev/'infra_timeout_recovery.before.py').write_text(recovery_text)
  recovery_path.write_text(recovery_new)
  watchers=[]
  for procdir in Path('/proc').iterdir():
   if not procdir.name.isdigit():continue
   try:
    argv=[a.decode(errors='replace') for a in (procdir/'cmdline').read_bytes().split(b'\0') if a]
    if any(Path(a).name=='infra_timeout_recovery.py' for a in argv) and (procdir/'cwd').resolve()==ROOT:watchers.append(int(procdir.name))
   except (FileNotFoundError,PermissionError,ProcessLookupError):pass
  for watcher in watchers:os.kill(watcher,signal.SIGINT)
  for attempt in range(150):
   if not any(Path('/proc',str(w)).exists() for w in watchers):break
   time.sleep(0.2)
  assert not any(Path('/proc',str(w)).exists() for w in watchers),'Old queued recovery did not exit'
  if alive(RECOVERY):subprocess.run(['tmux','kill-session','-t',RECOVERY],check=True)
  launch(RECOVERY,ROOT,['infra_timeout_recovery.py'],'infra_timeout_recovery.log',12)
  def save():
   dump(STATE,{'phase':'complete' if all(p['phase']=='confirmed' for p in plans) else 'draining_and_resuming','plans':[{k:(str(p[k]) if isinstance(p[k],Path) else p[k]) for k in ('method','root','session','workers','old_pid','phase')} for p in plans],'revision':str(rev),'time':time.time()})
  for p in plans:
   os.kill(p['old_pid'],signal.SIGINT);p['phase']='draining'
  save();print('PARENT_ONLY_SIGINT_SENT_DRAINING',flush=True)
  while any(p['phase']!='confirmed' for p in plans):
   for p in plans:
    r=p['root']
    if p['phase']=='draining':
     if same_process(p) or alive(p['session']):continue
     args=['run.py']+(['SoL-Pi'] if p['method']=='SoL-Pi' else [])
     launch(p['session'],r,args,p['log'],p['workers']);p['phase']='starting';save()
    elif p['phase']=='starting':
     state_path=r/'state.json' if p['method']=='MolClaw' else r/'state'/(p['method']+'.json')
     state=json.loads(state_path.read_text())
     if state.get('workers')==p['workers'] and state.get('phase') in ('full','complete','attention_required'):
      assert processes(p) or state['phase']!='full','New pipeline not live'
      assert sha(r/'jobs.json')==p['jobs_sha256'] and sha(r/'common.py')==p['common_sha256']
      assert all((r/filename).exists() and sha(r/filename)==h for filename,h in p['preserved'].items()),'Existing results changed'
      p['phase']='confirmed'
      dump(r/'concurrency_confirmation.json',{'workers':p['workers'],'previous_workers':4,'phase':state['phase'],'existing_results_preserved':len(p['preserved']),'jobs_unchanged':True,'evaluation_unchanged':True,'time':time.time(),'revision':str(rev)})
      print('CONFIRMED',p['method'],p['workers'],flush=True);save()
     elif state.get('workers')==p['workers'] and state.get('phase')=='failed':
      raise RuntimeError('Restart failed for '+p['method']+': '+str(state.get('error')))
     elif not alive(p['session']):
      raise RuntimeError('Restart session exited for '+p['method'])
   time.sleep(2)
  (ROOT/'concurrency_restart_pending.json').unlink()
  save();print('CONCURRENCY_UPGRADE_COMPLETE',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  dump(STATE,{'phase':'failed','error':str(exc),'time':time.time()})
  (ROOT/'concurrency_restart_error.log').write_text(traceback.format_exc());raise
