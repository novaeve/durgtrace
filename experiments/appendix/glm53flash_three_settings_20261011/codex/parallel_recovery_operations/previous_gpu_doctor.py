import fcntl,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if (ROOT/'provider_hold.json').exists():raise SystemExit(0)
PY='/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python'
def alive(script,arg=None):
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:args=(p/'cmdline').read_bytes().split(b'\0')
  except OSError:continue
  if str(script).encode() in args and (arg is None or arg.encode() in args):return True
 return False
def launch(cmd,name):
 p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=(ROOT/(name+'_doctor.log')).open('a'),stderr=subprocess.STDOUT,start_new_session=True)
 with (ROOT/'service_recovery.jsonl').open('a') as f:f.write(json.dumps({'service':name,'pid':p.pid,'time':time.time()})+'\n')
with (ROOT/'doctor.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if not alive(ROOT/'molclaw/proxy_config.yaml'):
  launch(['/data2/chenfuxin/molclaw_20260924/isolated_env/bin/python','-u',str(ROOT/'molclaw/launch_proxy.py')],'MolClaw_proxy')
 for method,path,args,state in [
  ('agents',ROOT/'agents/run.py',None,ROOT/'agents/state.json'),
  ('SoL-Pi',ROOT/'lingo_sol/run.py','SoL-Pi',ROOT/'lingo_sol/state/SoL-Pi.json'),
  ('MolClaw',ROOT/'molclaw/run.py',None,ROOT/'molclaw/state.json'),
  ('Codex',ROOT/'codex/run_benchmark.py',None,ROOT/'codex/state.json'),
  ('GLM_direct',ROOT/'direct/run.py',None,ROOT/'direct/state.json'),
  ('GLM_direct_retry1120',ROOT/'direct/uncapped_retry1120/run_retry.py',None,ROOT/'direct/uncapped_retry1120/state.json')]:
  if method=='Codex' and not (ROOT/'codex/native_smoke.json').exists():continue
  if method=='GLM_direct' and not (ROOT/'direct/independent_validation.json').exists():continue
  if method=='GLM_direct_retry1120' and not (ROOT/'direct/uncapped_retry1120/manifest.json').exists():continue
  data=json.loads(state.read_text()) if state.exists() else {}
  if data.get('phase') in ('complete','attention_required','failed'):continue
  if not alive(path,args) and not alive(ROOT/'supervisor.py',method):launch([PY,'-u',str(ROOT/'supervisor.py'),method],method)
