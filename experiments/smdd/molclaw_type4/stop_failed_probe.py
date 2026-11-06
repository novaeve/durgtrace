from pathlib import Path
import os,signal
root=Path('/yimin/zlc/molclaw_type4_20261003')
for p in Path('/proc').glob('[0-9]*'):
 try:
  if p.stat().st_uid!=os.getuid() or (p/'cwd').resolve()!=root:continue
  argv=(p/'cmdline').read_bytes().split(bytes([0]))
  if argv[:2]!=[b'./proxy_env/bin/python',b'-']:continue
  fields=(p/'stat').read_text().split();parent=Path('/proc')/fields[3]
  if b'preflight/model_connection' not in (parent/'cmdline').read_bytes():continue
  os.kill(int(p.name),signal.SIGTERM);print('Stopped obsolete failed-proxy probe',p.name)
 except (OSError,ValueError):pass
