import os,signal,json
from pathlib import Path
root='/data2/chenfuxin/molclaw_pmo_20260929_v2'
selected=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  cwd=os.readlink(p/'cwd')
  cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  if cwd==root or cwd.startswith(root+'/') or (root+'/' in cmd and 'stop_v2.py' not in cmd and 'bash -c' not in cmd):selected.append(int(p.name))
 except OSError:pass
for state in Path(root).glob('control/*/0/state.json'):
 try:
  pid=json.loads(state.read_text()).get('pid')
  if pid and b'runner.py' in Path('/proc',str(pid),'cmdline').read_bytes():selected.append(pid)
 except (OSError,ValueError):pass
selected=sorted(set(selected))
for pid in selected:
 try:os.kill(pid,signal.SIGSTOP)
 except ProcessLookupError:pass
for pid in selected:
 try:os.kill(pid,signal.SIGTERM);os.kill(pid,signal.SIGCONT)
 except ProcessLookupError:pass
print(json.dumps({'stopped_v2_pids':selected}))
