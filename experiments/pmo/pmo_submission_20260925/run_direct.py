"""Plain LLM independent sampling, without parents, search, or feedback."""
import argparse
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent
LEGACY = Path('/data2/chenfuxin/pmo_1k_20260924')
sys.path.insert(0, str(LEGACY))
# Reuse only audited API transport, canonicalization and oracle dependencies.
# Do not import adapters, the legacy Ledger, initialization, or search runner.
from pmo_common import Relay, LongTruncation, canonical, make_oracle, dump, sha, MODEL
from task_specs import TASKS
from submission_budget import SubmissionLedger


def task_prompt(task):
    return (f'PMO molecular optimization objective: {task}. {TASKS[task][1]} '
            'Scores range from 0 to 1; higher is better. '
            'Return only one candidate SMILES, without explanation.')


def job(task, smoke_limit=None):
    os.chdir(LEGACY)  # Existing, verified TDC oracle cache; no downloads/rewrites.
    for path, digest in json.loads((LEGACY/'prepared/dependencies.json').read_text()).items():
        if sha(path) != digest:
            raise RuntimeError('Verified oracle dependency changed: '+path)
    out = ROOT/'runs/deepseek'/task/'0'
    out.mkdir(parents=True, exist_ok=True)
    with (out/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'result.json').exists():
            previous = json.loads((out/'result.json').read_text())
            if previous['status'] in ('complete', 'skipped_long_truncation'):
                return previous
        config = {'method': 'deepseek_direct_independent_sampling', 'task': task,
                  'replicate': 0, 'model': MODEL, 'temperature': 0,
                  'enable_thinking': False, 'submission_budget': 1000,
                  'initialization': None, 'history': None, 'score_feedback': False,
                  'search': None, 'messages': [{'role': 'user', 'content': task_prompt(task)}],
                  'source_hashes': {p.name: sha(p) for p in
                                    [ROOT/'run_direct.py', ROOT/'submission_budget.py',
                                     LEGACY/'task_specs.py', LEGACY/'pmo_common.py']}}
        if (out/'config.json').exists():
            if json.loads((out/'config.json').read_text()) != config:
                raise RuntimeError('Configuration changed; do not resume silently')
        else:
            dump(out/'config.json', config)
        ledger = SubmissionLedger(out/'answers.jsonl', canonical,
                                  make_oracle(TASKS[task][0]))
        relay = Relay(out)
        state_path = out/'state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {'attempt': 0}
        start = time.time()
        try:
            while not ledger.exhausted:
                if len(relay.long_truncations) >= 3:
                    status = 'skipped_long_truncation'
                    break
                attempt = state['attempt']
                try:
                    raw = relay.complete(config['messages'], f'direct/{attempt}')
                    # Only output-format cleanup. No extraction of extra candidates,
                    # selection, molecule repair or model retry for invalid answers.
                    answer = raw.strip()
                    if answer.startswith('```') and answer.endswith('```'):
                        lines = answer.splitlines()
                        if len(lines) >= 3:
                            answer = '\n'.join(lines[1:-1]).strip()
                    ledger.submit(answer, f'direct/{attempt}')
                except LongTruncation:
                    # A truncated response is still one failed submission attempt.
                    # Never send the unbounded partial SMILES through RDKit.
                    ledger.submit(None, f'direct/{attempt}')
                state = {'attempt': attempt + 1}
                dump(state_path, state)
                progress = {'status': 'running', 'time': time.time(), **ledger.metrics()}
                dump(out/'progress.json', progress)
                if smoke_limit and len(ledger.rows) >= smoke_limit:
                    progress['status'] = 'pilot_checked'
                    dump(out/'progress.json', progress)
                    return progress
            else:
                status = 'complete'
            result = {'status': status, 'time': time.time(),
                      'seconds_this_process': time.time()-start,
                      **ledger.metrics(), **relay.usage()}
            dump(out/'result.json', result)
            return result
        except Exception as error:
            dump(out/'error.json', {'time': time.time(),
                                   'error_type': type(error).__name__,
                                   'error': str(error)[:250]})
            raise


def suite():
    with (ROOT/'suite.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pilot = job('qed', smoke_limit=3)
        if pilot.get('unique_valid', 0) == 0 or pilot['status'] == 'skipped_long_truncation':
            raise RuntimeError('Direct-model smoke check produced no valid molecule')
        dump(ROOT/'pilot_validation.json', {'task': 'qed', 'time': time.time(),
                                          'result': pilot, 'reuse_same_config': True})
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(job, task): task for task in TASKS}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                print(json.dumps({'task': futures[future], **result}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['suite', 'job'])
    parser.add_argument('--task', choices=list(TASKS), default='qed')
    args = parser.parse_args()
    if args.action == 'suite':
        suite()
    else:
        print(json.dumps(job(args.task)))
