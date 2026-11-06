from pathlib import Path
import json
import os
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
assert json.loads((root / 'preflight.json').read_text())['accepted']
assert json.loads((root / 'preflight/boundary_tests.json').read_text())['accepted']
pidfile = root / 'pipeline.pid'
if pidfile.exists():
    old = Path('/proc') / pidfile.read_text().strip()
    if (old / 'cmdline').exists() and str(root / 'run.py').encode() in (old / 'cmdline').read_bytes():
        raise SystemExit('This pipeline is already running')
with (root / 'pipeline.log').open('a') as log:
    proc = subprocess.Popen([sys.executable, '-u', str(root / 'run.py'), 'pipeline'],
        cwd=root, env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
pidfile.write_text(str(proc.pid))
time.sleep(2)
print(json.dumps({'pid': proc.pid, 'poll': proc.poll(), 'mode': 'pilot acceptance -> full 23 tasks -> aggregate'}))
