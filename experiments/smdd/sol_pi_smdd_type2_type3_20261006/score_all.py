"""Original offline SMDD metrics; no score is returned to the native agent."""
from pathlib import Path
import collections
import fcntl
import importlib.util
import json
import sys
import time
import traceback
import run
import runtime
from runtime import dump


def type2_score(root, tid):
    out, ev = root / 'runs/solpi' / tid, root / 'evaluation/solpi' / tid
    ev.mkdir(parents=True, exist_ok=True)
    metric = run.ROOT / 'source/pharmacophore_3d.py'
    solution = out / 'solution.csv'
    if not solution.exists():
        result = {'score': 0, 'n_correct': 0, 'n_required': 3, 'reason': 'missing_submission'}
    else:
        command = ('import sys,json; sys.path.insert(0,"/eval"); '
                   'from pharmacophore_3d import evaluate_3d_pharmacophore; '
                   'print(json.dumps(evaluate_3d_pharmacophore("/eval/solution.csv","/eval/ground_truth.json")))')
        work = ev / 'metric_work'
        text, code = runtime.isolated(['python', '-c', command], work, timeout=300, binds=[
            '--ro-bind', str(metric), '/eval/pharmacophore_3d.py',
            '--ro-bind', str(solution), '/eval/solution.csv',
            '--ro-bind', str(root / 'tasks' / tid / 'ground_truth.json'), '/eval/ground_truth.json'])
        (ev / 'metric.log').write_text(text)
        if code:
            # Malformed CSV is a failed prediction; other evaluator failures need inspection.
            if any(name in text for name in ('ValueError', 'IndexError', 'KeyError')):
                result = {'score': 0, 'n_correct': 0, 'n_required': 3, 'reason': 'invalid_submission_format'}
            else:
                raise RuntimeError('Type2 official metric failed; see metric.log')
        else:
            result = json.loads(text.strip().splitlines()[-1])
    result.update(task=tid, passed=result['score'] == 1, status='passed' if result['score'] == 1 else 'failed')
    dump(ev / 'result.json', result)
    return result


def type3_evaluator(root):
    path = run.ROOT / 'source/type3_evaluate.py'
    spec = importlib.util.spec_from_file_location('solpi_original_type3_evaluate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT, module.UPSTREAM = root, runtime.UPSTREAM
    module.gpu_run = runtime.gpu_run
    return module


def summarize(kind, root, count):
    rows = [json.loads(p.read_text()) for p in (root / 'evaluation/solpi').glob('*/result.json')]
    result = {'kind': kind, 'expected': count, 'evaluated': len(rows),
              'statuses': dict(collections.Counter(row['status'] for row in rows)), 'time': time.time()}
    if kind == 'type2':
        result.update(correct_points=sum(row.get('n_correct', 0) for row in rows), point_denominator=75,
                      passed_tasks=sum(row.get('passed', False) for row in rows), task_denominator=25)
    dump(root / 'evaluation/summary.json', result)
    return result


def main(kind):
    root = run.ROOT / kind
    count = 25 if kind == 'type2' else 52
    (root / 'evaluation').mkdir(exist_ok=True)
    evaluator = type3_evaluator(root) if kind == 'type3' else None
    try:
        with (root / 'score.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            while True:
                for path in sorted((root / 'runs/solpi').glob('*/result.json')):
                    tid = path.parent.name
                    destination = root / 'evaluation/solpi' / tid / 'result.json'
                    if destination.exists():
                        continue
                    if kind == 'type2':
                        result = type2_score(root, tid)
                    else:
                        result = evaluator.evaluate(tid, 'solpi')
                        if result['status'] == 'errored' and any(step.get('name') == 'Validity' and step.get('status') == 'failed' for step in result.get('steps', [])):
                            dump(destination.with_name('raw_result.json'), result)
                            result['status'] = 'failed'
                            result['adjudication'] = {'reason': 'Invalid molecule counts as failed', 'raw_result': 'raw_result.json'}
                            dump(destination, result)
                        if result['status'] == 'errored':
                            raise RuntimeError('Official Type3 evaluator infrastructure failure; inspect results')
                    print(json.dumps({'kind': kind, 'task': tid, 'status': result['status']}), flush=True)
                    summarize(kind, root, count)
                summary = summarize(kind, root, count)
                if summary['evaluated'] == count:
                    dump(root / 'scoring_exit.json', {'finished': True, 'time': time.time()})
                    break
                exitfile = root / 'generation_exit.json'
                if exitfile.exists() and not json.loads(exitfile.read_text())['finished']:
                    raise RuntimeError('Generation stopped for infrastructure inspection')
                time.sleep(15)
    except Exception as exc:
        (root / 'scoring_error.log').write_text(traceback.format_exc())
        dump(root / 'scoring_exit.json', {'finished': False, 'error': type(exc).__name__, 'time': time.time()})
        raise


if __name__ == '__main__':
    main(sys.argv[1])
