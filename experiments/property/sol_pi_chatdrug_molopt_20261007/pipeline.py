"""Launch only after native-tool and original-protocol checks pass."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback
import run
import preflight
import score

ROOT = Path(__file__).resolve().parent
native_execute = run.execute


def admitted_execute(case, stage, prompt_override=None):
    destination = ROOT / 'runs' / stage / case['id']
    wait_record = ROOT / 'admission' / stage / case['id'] / 'wait.json'
    while not (destination / 'result.json').exists() and shutil.disk_usage(ROOT).free < 20 * 1024**3:
        run.dump(wait_record, {'reason': 'disk_free_below_20GiB', 'updated': time.time(),
                              'native_budget_started': False})
        time.sleep(30)
    if wait_record.exists():
        wait_record.unlink()
    row = native_execute(case, stage, prompt_override)
    # Evaluate only after the complete native episode; one candidate, no feedback.
    if stage == 'full':
        evaluate, _ = score.original_evaluator()
        result = evaluate(case, row.get('candidate') if row['status'] == 'complete' else None)
        run.dump(destination / 'evaluation.json', {'protocol': 'original', 'evaluation_calls': 1, 'score': result})
    return row


def phase(name):
    run.dump(ROOT / 'phase.json', {'phase': name, 'updated': time.time(), 'pid': os.getpid()})


def main():
    run.execute = admitted_execute
    try:
        phase('preflight')
        preflight.main()
        phase('pilot')
        report = run.main('pilot')
        assert report['processed'] == 2 and all(g['runtime_errors'] == 0 for g in report['groups'].values()), report
        preflight.validate_runtime('pilot')
        score.main('pilot')
        phase('full')
        report = run.main('full')
        assert report['processed'] == 7100, report
        phase('scoring')
        score.main('full')
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        assert run.sha(ROOT / 'original_cases.json') == manifest['case_sha256']
        for file, digest in manifest['source_hashes'].items():
            assert run.sha(ROOT / file) == digest, file
        phase('complete')
        run.dump(ROOT / 'pipeline_exit.json', {'status': 'complete', 'updated': time.time()})
    except Exception:
        (ROOT / 'pipeline_exception.log').write_text(traceback.format_exc())
        phase('failed')
        run.dump(ROOT / 'pipeline_exit.json', {'status': 'failed', 'updated': time.time()})
        raise


if __name__ == '__main__':
    main()
