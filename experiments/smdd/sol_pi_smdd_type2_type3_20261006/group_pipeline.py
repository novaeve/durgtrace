from pathlib import Path
import collections
import concurrent.futures
import fcntl
import hashlib
import json
import sys
import time
import traceback
import run
import preflight
from runtime import dump


def progress(kind, cases):
    root = run.ROOT / kind
    rows = [json.loads(p.read_text()) for p in (root / 'runs/solpi').glob('*/result.json')]
    report = {'kind': kind, 'expected': len(cases), 'processed': len(rows),
              'statuses': dict(collections.Counter(row['status'] for row in rows)),
              'submitted': sum(row.get('submitted', False) for row in rows), 'time': time.time()}
    dump(root / 'progress.json', report)
    return report


def main(kind):
    root = run.ROOT / kind
    cases = json.loads((root / 'public_cases.json').read_text())
    try:
        with (root / 'run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            dump(root / 'pipeline_state.json', {'phase': 'preflight', 'time': time.time()})
            preflight.check(kind)
            dump(root / 'pipeline_state.json', {'phase': 'full', 'time': time.time()})
            progress(kind, cases)
            iterator = iter(cases)
            with concurrent.futures.ThreadPoolExecutor(2 if kind == 'type2' else 1) as pool:
                pending = set()
                for _ in range(2 if kind == 'type2' else 1):
                    case = next(iterator, None)
                    if case is not None:
                        pending.add(pool.submit(run.job, kind, case))
                while pending:
                    done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        result = future.result()
                        progress(kind, cases)
                        if result['status'] == 'infrastructure_error':
                            raise RuntimeError('Infrastructure failure; stopped for inspection: ' + result['task'])
                        case = next(iterator, None)
                        if case is not None:
                            pending.add(pool.submit(run.job, kind, case))
            report = progress(kind, cases)
            assert report['processed'] == len(cases)
            dump(root / 'generation_exit.json', {'finished': True, 'processed': len(cases), 'time': time.time()})
            dump(root / 'pipeline_state.json', {'phase': 'generation_complete', 'time': time.time()})
    except Exception as exc:
        (root / 'pipeline_error.log').write_text(traceback.format_exc())
        dump(root / 'generation_exit.json', {'finished': False, 'error': type(exc).__name__, 'time': time.time()})
        dump(root / 'pipeline_state.json', {'phase': 'failed', 'error': type(exc).__name__, 'time': time.time()})
        raise


if __name__ == '__main__':
    main(sys.argv[1])
