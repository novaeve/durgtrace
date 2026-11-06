from pathlib import Path
import json
import os
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
assert (root / 'manifest.json').exists()
started = []
for kind in ('type2', 'type3'):
    folder = root / kind
    for role, filename in [('generation', 'group_pipeline.py'), ('scoring', 'score_all.py')]:
        pidfile = folder / f'{role}.pid'
        if pidfile.exists():
            cmd = Path('/proc') / pidfile.read_text().strip() / 'cmdline'
            if cmd.exists() and str(root / filename).encode() in cmd.read_bytes():
                raise RuntimeError(f'{kind} {role} already running')
            raise RuntimeError(f'{kind} {role} was previously started; inspect before relaunching')
        with (folder / f'{role}.log').open('a') as log:
            proc = subprocess.Popen([sys.executable, '-u', str(root / filename), kind], cwd=root,
                    env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        pidfile.write_text(str(proc.pid))
        started.append({'kind': kind, 'role': role, 'pid': proc.pid})
time.sleep(2)
print(json.dumps({'started': started, 'type2_tasks': 25, 'type3_tasks': 52}))
