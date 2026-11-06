import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
assert str(ROOT).startswith('/data/chenfuxin/sol_pi_chatdrug_molopt_20261007')
assert sys.prefix == '/data2/chenfuxin/chatdrug_generalization_20260920/venv'
with (ROOT / 'launch.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    pidfile = ROOT / 'pipeline.pid'
    if pidfile.exists():
        pid = int(pidfile.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError(f'Pipeline already running: {pid}')
    assert not (ROOT / 'pipeline_exit.json').exists(), 'Review the previous exit before restarting'
    with (ROOT / 'pipeline.log').open('a') as log:
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', PYTHONPATH='')
        process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'pipeline.py')], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   env=env, start_new_session=True)
    pidfile.write_text(str(process.pid))
    time.sleep(2)
    assert process.poll() is None, (ROOT / 'pipeline.log').read_text()[-3000:]
    proof = {'pid': process.pid, 'root': str(ROOT), 'started': time.time(),
             'counts': {'ChatDrug-MolEdit-28': 5600, 'S2-miniMolOpt': 1500}, 'protocol': 'original'}
    (ROOT / 'launch.json').write_text(json.dumps(proof, indent=2))
    print(json.dumps(proof))
