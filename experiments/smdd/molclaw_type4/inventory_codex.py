import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
c=manage.connect(sys.argv[1]);manage.execute(c,Path(__file__).with_name('inventory_codex_'+sys.argv[1]+'.py').read_text());c.close()
