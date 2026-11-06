from pathlib import Path
import json
import os
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
assert (root / 'manifest.json').exists()
pidfile = root / 'pipeline.pid'
if pidfile.exists():
    path = Path('/proc') / pidfile.read_text().strip() / 'cmdline'
    if path.exists() and str(root / 'controller.py').encode() in path.read_bytes():
        raise SystemExit('The eleven-case rerun is already running')
    raise SystemExit('Previously started rerun; inspect before relaunching')
with (root / 'pipeline.log').open('a') as log:
    proc = subprocess.Popen([sys.executable, '-u', str(root / 'controller.py')], cwd=root,
             env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
pidfile.write_text(str(proc.pid))
time.sleep(2)
print(json.dumps({'pid': proc.pid, 'poll': proc.poll(), 'tasks': 11, 'workers': 2}))
