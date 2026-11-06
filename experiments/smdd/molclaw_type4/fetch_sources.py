import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'gpu-scheduling-20261001'))
import manage
c=manage.connect('gpu');s=c.open_sftp()
for src,name in [('/data2/chenfuxin/smdd_type3_harness_20261001/run.py','source_run.py'),('/data2/chenfuxin/smdd_type3_transfer_20260930/runtime.py','source_runtime.py'),('/data2/chenfuxin/smdd_type3_transfer_20260930/evaluate.py','source_evaluate.py'),('/data2/chenfuxin/smdd_type3_transfer_20260930/eval_bridge.py','eval_bridge.py')]:
 s.get(src,str(ROOT/name))
 print(name)
s.close();c.close()
