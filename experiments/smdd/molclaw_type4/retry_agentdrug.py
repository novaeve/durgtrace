import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
c=manage.connect('cpu')
if len(sys.argv)>1:
 manage.execute(c,(Path(__file__).resolve().parent/sys.argv[1]).read_text());c.close();raise SystemExit(0)
code='''from pathlib import Path
import json,subprocess
r=Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929')
ids=['smdd_004_BCL6_20','smdd_004_BRD2_3','smdd_004_DHFR_16']
print(subprocess.getoutput('systemctl --user show smdd-type4-parallel.service -p ActiveState -p SubState -p MainPID -p ExecStart'))
print('TRANSPORT_SOURCE',(r/'transport_adapter.py').read_text())
for tid in ids:
 print('TASK',tid)
 for section in ['run','evaluator']:
  p=r/'agentdrug'/section/tid
  print(section, [(q.name,q.stat().st_size) for q in p.iterdir() if q.is_file()] if p.exists() else [])
  for name in ['agent_result.json','result.json']:
   if (p/name).exists():print(name,(p/name).read_text()[:1200])
 p=r/'agentdrug/logs'/(tid+'.log');print('LOG',p.read_text(errors='replace')[-2000:] if p.exists() else None)
'''
manage.execute(c,code);c.close()
