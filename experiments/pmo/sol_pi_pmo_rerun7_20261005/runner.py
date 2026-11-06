from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
TASKS = ['gsk3b', 'isomers_c7h8n2o2', 'median2', 'osimertinib_mpo',
         'ranolazine_mpo', 'sitagliptin_mpo', 'valsartan_smarts']


def execute():
    import run
    from segment_policy import check_policy
    assert check_policy()['accepted']
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    source = Path(manifest['source'])
    assert hashlib.sha256((source / 'run.py').read_bytes()).hexdigest() == manifest['source_run_sha256']
    for task in TASKS:
        original = json.loads((source / 'control/full' / task / '0/result.json').read_text())
        assert original['status'] == 'error' and 'truncated' in original['reason']
        assert original['oracle_submissions'] < 1000
    started = time.time()
    data = run.suite('full', tasks=TASKS)
    for task, digest in manifest['original_results'].items():
        assert hashlib.sha256((source / 'control/full' / task / '0/result.json').read_bytes()).hexdigest() == digest
    report = dict(finished=True, tasks=TASKS, planned=7, completed=data['completed'],
                  all_tasks_completed=data['completed'] == 7, started=started, ended=time.time(),
                  original_results_unchanged=True)
    run.dump(ROOT / 'rerun_exit.json', report)
    print(json.dumps(report), flush=True)


def start():
    pidfile = ROOT / 'pipeline.pid'
    if pidfile.exists():
        cmd = Path('/proc') / pidfile.read_text().strip() / 'cmdline'
        if cmd.exists() and str(ROOT / 'runner.py').encode() in cmd.read_bytes():
            raise SystemExit('The seven-task rerun is already running')
    assert not (ROOT / 'rerun_exit.json').exists(), 'Rerun already finished'
    with (ROOT / 'pipeline.log').open('a') as log:
        proc = subprocess.Popen([sys.executable, '-u', str(ROOT / 'runner.py'), 'run'],
                cwd=ROOT, env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    pidfile.write_text(str(proc.pid))
    time.sleep(2)
    print(json.dumps(dict(pid=proc.pid, poll=proc.poll(), tasks=TASKS, fresh_budget=1000)))


if __name__ == '__main__':
    if sys.argv[1:] == ['start']:
        start()
    elif sys.argv[1:] == ['run']:
        execute()
    else:
        raise SystemExit('Usage: runner.py start|run')
