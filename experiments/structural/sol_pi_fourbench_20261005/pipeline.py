from pathlib import Path
import json
import subprocess
import sys
import time
import traceback
import run
import preflight


def main():
    try:
        run.dump(run.ROOT / 'pipeline_state.json', {'phase': 'preflight', 'time': time.time()})
        subprocess.run([sys.executable, str(run.ROOT / 'test_policy.py')], check=True)
        preflight.main()
        run.dump(run.ROOT / 'pipeline_state.json', {'phase': 'pilot', 'time': time.time()})
        pilot = run.main('pilot')
        preflight.validate_runtime('pilot')
        assert pilot['processed'] == 10
        assert not any(g['runtime_errors'] for g in pilot['groups'].values()), 'Pilot infrastructure failure'
        import score
        score.main('pilot')
        run.dump(run.ROOT / 'pilot_acceptance.json', {'accepted': True, 'processed': 10,
                 'policy': 'infrastructure validation only; no correctness threshold', 'time': time.time()})
        run.dump(run.ROOT / 'pipeline_state.json', {'phase': 'full', 'time': time.time()})
        result = run.main('full')
        score.main('full')
        manifest = json.loads((run.ROOT / 'manifest.json').read_text())
        assert all(run.sha(Path(p)) == digest for p, digest in manifest['baseline_files'].items())
        run.dump(run.ROOT / 'pipeline_exit.json', {'finished': True, 'phase': 'complete',
                 'processed': result['processed'], 'expected': 3800, 'original_inputs_unchanged': True,
                 'time': time.time()})
        run.dump(run.ROOT / 'pipeline_state.json', {'phase': 'complete', 'time': time.time()})
    except Exception as exc:
        (run.ROOT / 'pipeline_error.log').write_text(traceback.format_exc())
        run.dump(run.ROOT / 'pipeline_exit.json', {'finished': False, 'phase': 'failed',
                 'error': type(exc).__name__, 'time': time.time()})
        run.dump(run.ROOT / 'pipeline_state.json', {'phase': 'failed', 'error': type(exc).__name__, 'time': time.time()})
        raise


if __name__ == '__main__':
    main()
