import concurrent.futures
import json
from pathlib import Path
import subprocess
import unittest
import continuous as c


if __name__ == '__main__':
    tests = unittest.defaultTestLoader.loadTestsFromName('test_continuous')
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if not result.wasSuccessful():
        raise SystemExit('Validation failed; full suite not started')
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(c.job, m, 'qed', 'pilot', 25, 100): m for m in c.METHODS}
        results = {}
        for future in concurrent.futures.as_completed(pending):
            method = pending[future]
            row = future.result()
            assert row['status'] == 'complete' and row['oracle_submissions'] == 25
            assert row['episodes'] > 1 and not row['auc_is_tail_filled']
            if method == 'chatdrug':
                episodes = c.ROOT/'pilot/chatdrug/qed/0/episodes'
                for path in episodes.glob('*/episode.json'):
                    trace = json.loads(path.read_text())['trace']
                    assert 'Invalid drug. Failed to evaluate.' not in trace.get('log', '')
            results[method] = row
            print('REAL_PILOT', method, json.dumps(row), flush=True)
    c.n.dump(c.ROOT/'real_pilot_validation.json', {
        'passed': True, 'unit_tests_passed': result.testsRun,
        'runner_sha': c.n.sha(c.ROOT/'continuous.py'), 'results': results})
    subprocess.run(['tmux', 'new-session', '-d', '-s', 'pmo-ref-free-1k',
                    'bash '+str(c.ROOT/'launch.sh')], check=True)
    print('OFFICIAL_CONTINUOUS_1K_SUITE_STARTED', c.ROOT, flush=True)
