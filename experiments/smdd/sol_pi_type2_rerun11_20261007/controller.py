from pathlib import Path
import collections
import concurrent.futures
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import run
import preflight
import gpu_slots
import score_all
from process_cleanup import stop_group
from runtime import dump

ROOT = Path(__file__).resolve().parent


def progress():
    cases = json.loads((ROOT / 'type2/public_cases.json').read_text())
    rows = [json.loads(p.read_text()) for p in (ROOT / 'type2/runs/solpi').glob('*/result.json')]
    scores = [json.loads(p.read_text()) for p in (ROOT / 'type2/evaluation/solpi').glob('*/result.json')]
    report = {'expected': 11, 'processed': len(rows), 'evaluated': len(scores),
              'statuses': dict(collections.Counter(row['status'] for row in rows)),
              'passed_tasks': sum(row.get('passed', False) for row in scores),
              'correct_points': sum(row.get('n_correct', 0) for row in scores),
              'point_denominator': 33, 'time': time.time()}
    dump(ROOT / 'progress.json', report)
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    source = Path(manifest['source'])
    combined = []
    for path in sorted((source / 'type2/runs/solpi').glob('*/result.json')):
        tid = path.parent.name
        new = ROOT / 'type2/runs/solpi' / tid / 'result.json'
        use_new = new.exists()
        generation = json.loads((new if use_new else path).read_text())
        score = ROOT / 'type2/evaluation/solpi' / tid / 'result.json' if use_new else source / 'type2/evaluation/solpi' / tid / 'result.json'
        evaluated = json.loads(score.read_text()) if score.exists() else None
        combined.append({'task': tid, 'source': 'rerun' if use_new else 'original',
                         'generation_status': generation['status'], 'score': evaluated})
    dump(ROOT / 'combined_latest_25.json', {'expected': 25, 'point_denominator': 75,
         'rerun_processed': len(rows), 'evaluated': sum(row['score'] is not None for row in combined),
         'passed_tasks': sum(bool(row['score'] and row['score'].get('passed')) for row in combined),
         'correct_points': sum(row['score'].get('n_correct', 0) if row['score'] else 0 for row in combined),
         'rows': combined, 'selection_policy': manifest['result_policy'], 'time': time.time()})
    return report


def execute(case):
    tid = case['id']
    out = ROOT / 'type2/runs/solpi' / tid
    out.mkdir(parents=True, exist_ok=True)
    # Check the same shared leases before charging any model or task-wall budget.
    with gpu_slots.acquire(ROOT / 'admission' / tid) as (gpu, descriptors):
        dump(out / 'admission.json', {'ready_gpu_at_admission': gpu, 'time': time.time()})
    with (out / 'worker.log').open('a') as log:
        proc = subprocess.Popen([sys.executable, '-u', str(ROOT / 'case_worker.py'), tid],
             cwd=ROOT, env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        code = proc.wait(timeout=3720)
    except subprocess.TimeoutExpired:
        stop_group(proc.pid)
        code = proc.wait(timeout=20)
    finally:
        cleanup = stop_group(proc.pid)
        dump(out / 'process_cleanup.json', cleanup)
    result = out / 'result.json'
    if not result.exists():
        dump(result, {'task': tid, 'kind': 'type2', 'method': 'solpi',
                      'status': 'infrastructure_error', 'error': 'worker_exit_without_result', 'exit_code': code})
    row = json.loads(result.read_text())
    if row['status'] != 'infrastructure_error':
        score_all.type2_score(ROOT / 'type2', tid)
    print(json.dumps({'task': tid, 'status': row['status']}), flush=True)
    return row


def main():
    try:
        with (ROOT / 'controller.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            dump(ROOT / 'pipeline_state.json', {'phase': 'preflight', 'time': time.time()})
            subprocess.run([sys.executable, str(ROOT / 'test_cleanup.py')], check=True)
            subprocess.run([sys.executable, str(ROOT / 'test_policy.py')], check=True)
            preflight.check('type2')
            cases = json.loads((ROOT / 'type2/public_cases.json').read_text())
            assert len(cases) == 11
            dump(ROOT / 'pipeline_state.json', {'phase': 'full', 'time': time.time()})
            progress()
            iterator = iter(cases)
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                pending = {pool.submit(execute, next(iterator)) for _ in range(2)}
                while pending:
                    done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        row = future.result()
                        progress()
                        if row['status'] == 'infrastructure_error':
                            raise RuntimeError('Infrastructure failure: ' + row['task'])
                        case = next(iterator, None)
                        if case is not None:
                            pending.add(pool.submit(execute, case))
            report = progress()
            manifest = json.loads((ROOT / 'manifest.json').read_text())
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in manifest['original_result_hashes'].items())
            dump(ROOT / 'pipeline_exit.json', {'finished': True, 'original_results_unchanged': True,
                                              **report, 'time': time.time()})
            dump(ROOT / 'pipeline_state.json', {'phase': 'complete', 'time': time.time()})
    except Exception as exc:
        (ROOT / 'pipeline_error.log').write_text(traceback.format_exc())
        dump(ROOT / 'pipeline_exit.json', {'finished': False, 'error': type(exc).__name__, 'time': time.time()})
        dump(ROOT / 'pipeline_state.json', {'phase': 'failed', 'time': time.time()})
        raise


if __name__ == '__main__':
    main()
