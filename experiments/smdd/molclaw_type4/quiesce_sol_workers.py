from pathlib import Path
import json,os,signal,time,shutil,subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004');repair=json.loads((r/'repair_current.json').read_text());a=Path(repair['archive']);s=json.loads((a/'scheduler_before.json').read_text())
assert subprocess.run(['systemctl','--user','is-active','sol-pi-type4-a100.service'],text=True,capture_output=True).stdout.strip()!='active'
done=[]
for it in s['active']['solpi']:
 out=r/'runs/solpi'/it['task'];pid=it['pid'];proc=Path(f'/proc/{pid}')
 if (out/'record.json').exists():print('ALREADY_FINISHED',it['task']);continue
 args=(proc/'cmdline').read_bytes().decode().split(chr(0));assert str(r/'worker.py') in args and it['task'] in args
 fields=(proc/'stat').read_text().split(') ')[1].split();assert fields[19]==it['identity']
 os.kill(pid,signal.SIGSTOP)
 pinfo=json.loads((out/'process.json').read_text());native=pinfo['pid'];np=Path(f'/proc/{native}/cmdline')
 if np.exists():
  cmd=np.read_bytes().decode();assert str(out/'workspace') in cmd and 'bwrap' in cmd
  os.killpg(native,signal.SIGTERM)
 deadline=time.monotonic()+20
 while not (out/'result.json').exists() and time.monotonic()<deadline:time.sleep(0.2)
 assert (out/'result.json').exists(),'Native wrapper did not checkpoint; worker remains safely stopped'
 state=json.loads((out/'result.json').read_text());assert 'calls' in state
 shutil.copy2(out/'result.json',a/'task_before'/it['task']/'interrupted_result.json')
 (out/'resume_state.json').write_text(json.dumps(state,indent=2))
 (out/'result.json').rename(a/'task_before'/it['task']/'result_before_resume.json')
 os.kill(pid,signal.SIGKILL)
 done.append({'task':it['task'],'saved_state':state,'worker_pid':pid});print('CHECKPOINTED',it['task'],{k:state[k] for k in ['calls','tokens','admet_calls','boltz_calls','submitted']})
(a/'quiesced.json').write_text(json.dumps(done,indent=2));print('QUIESCED_SOL_ONLY',len(done))
