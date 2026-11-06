"""Reuse the original evaluator, isolated from the generation context."""
from pathlib import Path
import ast
import collections
import json
import sys
import run

ROOT = Path(__file__).resolve().parent
CHAT = Path('/data2/chenfuxin/chatdrug_generalization_20260920')


def original_evaluator():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for path, digest in manifest['frozen_scorer_dependencies'].items():
        assert run.sha(Path(path)) == digest, path
    sys.path.insert(0, str(CHAT))
    import pilot as p
    source = ROOT / 'source/original_full_experiment.py'
    nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'score']
    assert len(nodes) == 1
    namespace = {'p': p}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['score'], p


def main(stage):
    evaluate, p = original_evaluator()
    selected = run.cases()
    if stage == 'pilot':
        selected = [next(case for case in selected if case['benchmark'] == name) for name in ['ChatDrug', 'S2-mini']]
    groups, scored = {}, []
    for case in selected:
        group = groups.setdefault(case['benchmark'], collections.Counter())
        group['expected'] += 1
        path = ROOT / 'runs' / stage / case['id'] / 'result.json'
        if not path.exists():
            continue
        row = json.loads(path.read_text())
        candidate = row.get('candidate') if row['status'] == 'complete' else None
        evaluation_path = path.parent / 'evaluation.json'
        if evaluation_path.exists():
            recorded = json.loads(evaluation_path.read_text())
            assert recorded['protocol'] == 'original' and recorded['evaluation_calls'] == 1
            result = recorded['score']
        else:
            result = evaluate(case, candidate)
            run.dump(evaluation_path, {'protocol': 'original', 'evaluation_calls': 1, 'score': result})
        group['processed'] += 1
        group['success'] += bool(result['success'])
        group['valid'] += bool(result['valid'])
        group['runtime_noncomplete'] += row['status'] != 'complete'
        scored.append({'id': case['id'], 'benchmark': case['benchmark'], 'bucket': case['bucket'], 'score': result})
    for group in groups.values():
        group['success_rate_full_denominator'] = group['success'] / group['expected']
        group['valid_rate_full_denominator'] = group['valid'] / group['expected']
    report = {'protocol': 'original', 'rdkit_version': p.rdkit.__version__, 'groups': groups, 'rows': scored}
    run.dump(ROOT / 'runs' / stage / 'scores.json', report)
    print(json.dumps({'stage': stage, 'protocol': 'original', 'groups': groups}), flush=True)
    return report


if __name__ == '__main__':
    main(sys.argv[1])
