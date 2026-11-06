from pathlib import Path
import json
import os
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
assert (root / 'manifest.json').exists(), 'Run prepare.py first'
pidfile = root / 'pipeline.pid'
if pidfile.exists():
    cmd = Path('/proc') / pidfile.read_text().strip() / 'cmdline'
    if cmd.exists() and str(root / 'pipeline.py').encode() in cmd.read_bytes():
        raise SystemExit('The four-benchmark pipeline is already running')
assert not (root / 'pipeline_exit.json').exists(), 'Pipeline previously ended; inspect before relaunching'
with (root / 'pipeline.log').open('a') as log:
    proc = subprocess.Popen([sys.executable, '-u', str(root / 'pipeline.py')], cwd=root,
            env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
pidfile.write_text(str(proc.pid))
time.sleep(2)
print(json.dumps({'pid': proc.pid, 'poll': proc.poll(), 'case_count': 3800,
                  'pipeline': 'tool smoke -> 10-case pilot -> full frozen cases -> offline scores'}))
