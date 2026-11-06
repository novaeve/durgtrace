"""One-time maintenance: stop only this experiment's process tree."""
import os
import signal
import json
from pathlib import Path
root=Path('/data2/chenfuxin/molclaw_pmo_20260929_v3')
processes={}
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        stat=(p/'stat').read_text().rsplit(')',1)[1].split()
        processes[int(p.name)]=(int(stat[1]),cmd,os.readlink(p/'cwd'))
    except OSError:pass
selected=set()
for pid,(ppid,cmd,cwd) in processes.items():
    if 'runner.py' in cmd and (cwd==str(root) or str(root) in cmd):selected.add(pid)
for state in root.glob('control/*/0/state.json'):
    pid=json.loads(state.read_text()).get('pid')
    if pid in processes and 'runner.py' in processes[pid][1]:selected.add(pid)
# Freeze parents before collecting descendants so no new jobs can start.
for pid in selected:
    try:os.kill(pid,signal.SIGSTOP)
    except ProcessLookupError:pass
changed=True
while changed:
    changed=False
    for pid,(ppid,cmd,cwd) in processes.items():
        if ppid in selected and pid not in selected:selected.add(pid);changed=True
for pid in selected:
    try:os.kill(pid,signal.SIGSTOP)
    except ProcessLookupError:pass
for pid in selected:
    try:os.kill(pid,signal.SIGTERM);os.kill(pid,signal.SIGCONT)
    except ProcessLookupError:pass
print(json.dumps({'stopped':sorted(selected)}))
