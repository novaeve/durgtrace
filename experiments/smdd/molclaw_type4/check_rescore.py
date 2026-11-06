import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
c=manage.connect('gpu')
manage.execute(c,"""from pathlib import Path
import subprocess
r=Path('/data2/chenfuxin/smdd_rescore_20261004')
print('DRIVER', (r/'driver.log').read_text()[-3000:])
for p in r.glob('jobs/*/*/rescore.log'):
 print(p.parent.name,p.read_text()[-700:])
for p in r.glob('jobs/*/*/evaluation/container.log'):
 print('EVAL',p.parent.parent.name,p.read_text()[-350:])
print(subprocess.getoutput('nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader'))
""");c.close()
