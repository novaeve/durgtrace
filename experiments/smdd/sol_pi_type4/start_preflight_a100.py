from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect()
remote.py(c,"""from pathlib import Path
import json,subprocess,os
r=Path('/yimin/zlc/sol_pi_type4_20261004');assert json.loads((r/'source_validation.json').read_text())['passed']
with (r/'preflight.log').open('w') as log:
 p=subprocess.Popen(['/yimin/zlc/molclaw_type4_20261003/rootfs/opt/conda/bin/python','-u',str(r/'preflight.py')],cwd=r,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('A100_PREFLIGHT_PID',p.pid)
""");c.close()
