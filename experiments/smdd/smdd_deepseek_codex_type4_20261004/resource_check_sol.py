from pathlib import Path
import subprocess,json,pwd,os
print('GPU',subprocess.getoutput('nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader'))
for p in [Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004/scheduler_status.json'),Path('/data2/chenfuxin/sol_pi_pmo_20261004/manifest.json')]:
 if p.exists():print('STATUS',p,p.read_text()[:2500])
r=Path.home()/'SoL-Pi'
print('SOL',r,r.exists())
if r.exists():
 print('COMMIT',subprocess.getoutput('git -C '+str(r)+' rev-parse HEAD'))
 print('PI_PACKAGE',json.loads((r/'node_modules/@earendil-works/pi-coding-agent/package.json').read_text())['version'])
 for name in ['AGENTS.md','docs/compatibility.md']:
  print('SOURCE',name,(r/name).read_text()[:4500])
print('DISK',subprocess.getoutput('df -h /data2'))
