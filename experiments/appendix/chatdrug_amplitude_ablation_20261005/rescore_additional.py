"""Offline final-output ablation. No model imports or API requests.

Run with the original experiment's RDKit environment on the server.
Original result files are read only; outputs go to a separate directory.
"""
import argparse
import ast
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
import rdkit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='/data2/chenfuxin')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    base = Path(args.base)
    experiment = base / 'chatdrug_generalization_20260920'
    evaluator = experiment / 'upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py'
    spec = importlib.util.spec_from_file_location('frozen_chatdrug_evaluator', evaluator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    s2file = experiment / 'upstream/S2-TOMG-Bench/utils/evaluation.py'
    node = next(n for n in ast.parse(s2file.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'mol_prop')
    namespace = {'Chem': Chem, 'Descriptors': Descriptors}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(s2file), 'exec'), namespace)
    mol_prop = namespace['mol_prop']
    RDLogger.DisableLog('rdApp.*')
    cases = json.loads((experiment / 'prepared_full/cases.json').read_text())
    assert len(cases) == 7100 and len({c['id'] for c in cases}) == 7100
    roots = {'MolLingo_single': base / 'molingo_20260922/runs/single_bailian_full',
             'MolClaw': base / 'molclaw_20260924/runs/full'}
    groups = collections.defaultdict(collections.Counter)
    rows, issues, sources = [], [], {}
    for agent, root in roots.items():
        source_hash = hashlib.sha256()
        for case in cases:
            path = root / case['id'] / 'result.json'
            raw = path.read_bytes() if path.exists() else b''
            source_hash.update(case['id'].encode() + b'\0' + raw + b'\0')
            result = json.loads(raw) if raw else {}
            complete = result.get('status') == 'complete'
            if agent in ['MolLingo_single', 'MolClaw']:
                stored = result.get('score', {})
            else:
                arm = 'chatdrug' if agent == 'ChatDrug' else 'direct'
                stored = result.get('arms', {}).get(arm, {})
            candidate = stored.get('candidate')
            old_success = new_success = valid = False
            if complete:
                assert result['case'] == case, str(path)
                if case['benchmark'] == 'ChatDrug':
                    if candidate and Chem.MolFromSmiles(candidate) is not None:
                        _, _, old_answer = module.evaluate_molecule(
                            case['smiles'], candidate, case['task'], case['thresholds'])
                        _, _, new_answer = module.evaluate_molecule(
                            case['smiles'], candidate, case['task'], [0] * len(case['objectives']))
                        valid = old_answer != -1
                        old_success = valid and bool(old_answer)
                        new_success = valid and bool(new_answer)
                else:
                    prop = {'LogP': 'logP', 'QED': 'qed', 'MR': 'MR'}[case['property']]
                    before = mol_prop(case['smiles'], prop)
                    after = mol_prop(candidate, prop) if candidate else None
                    valid = after is not None
                    old_success = new_success = valid and (
                        after > before if case['direction'] == 'higher' else after < before)
                assert valid == bool(stored.get('valid')), (agent, case['id'], 'validity mismatch')
                assert old_success == bool(stored.get('success')), (agent, case['id'], 'original mismatch')
                delta_success = bool(valid and stored.get('property_deltas') and
                                     all(d > 0 for d in stored['property_deltas']))
                assert new_success == delta_success, (agent, case['id'], 'delta mismatch')
                assert not old_success or new_success
            else:
                issues.append({'agent': agent, 'id': case['id'],
                               'status': result.get('status', 'missing'), 'error': result.get('error')})
            labels = [case['benchmark']]
            if case['benchmark'] == 'ChatDrug':
                labels += ['ChatDrug_' + case['constraint'], 'ChatDrug_task_' + str(case['task']),
                           'ChatDrug_single' if len(case['objectives']) == 1 else 'ChatDrug_multi']
                if case['task'] in [101, 102, 103, 104]:
                    labels += ['ChatDrug_LogP_QED']
            else:
                labels += ['S2_' + case['property']]
                if case['property'] in ['LogP', 'QED']:
                    labels += ['S2_LogP_QED']
            for label in labels:
                g = groups[(agent, label)]
                g['expected'] += 1
                g['complete'] += complete
                g['valid'] += valid
                g['original_success'] += old_success
                g['direction_only_success'] += new_success
            rows.append({'agent': agent, 'id': case['id'], 'benchmark': case['benchmark'],
                         'task': case['task'], 'setting': case['constraint'], 'complete': complete,
                         'candidate': candidate, 'original_success': old_success,
                         'direction_only_success': new_success})
        sources[agent] = {'root': str(root), 'result_bytes_sha256': source_hash.hexdigest()}
    summary_groups = []
    for (agent, label), counts in sorted(groups.items()):
        g = dict(counts)
        g.update(agent=agent, group=label,
                 original_rate=g['original_success'] / g['expected'],
                 direction_only_rate=g['direction_only_success'] / g['expected'],
                 rescued=g['direction_only_success'] - g['original_success'])
        summary_groups.append(g)
    summary = {'protocol': 'Re-score saved FINAL outputs; retain validity, all objective directions, and original parsers. Set ChatDrug thresholds to zero. Equality fails. Missing/error cases fail. No candidate reselection.',
               'model_recorded_in_original_manifest': 'deepseek-v4.1-flash via Alibaba Bailian',
               'rdkit_version': rdkit.__version__, 'sources': sources,
               'evaluator_sha256': hashlib.sha256(evaluator.read_bytes()).hexdigest(),
               's2_properties_sha256': hashlib.sha256(s2file.read_bytes()).hexdigest(),
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'validation': 'All completed rows matched recomputed original success/validity; zero-threshold scores matched stored signed deltas; all original successes retained.',
               'groups': summary_groups, 'issues': issues,
               'limits': ['Original threshold-dependent agent feedback/stopping/retrieval remains in the saved trajectories.',
                          'ChatDrug: 14 tasks x 2 settings x 200 inputs; S2: LogP/QED/MR single targets, 500 each.',
                          'Loose and strict outputs remain separate runs in the 5600 denominator; do not treat them as 5600 unique molecular tasks.',
                          'Original source evaluator does not impose a numerical similarity cutoff.']}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (out / 'rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    print(json.dumps({'rdkit': rdkit.__version__, 'groups': [g for g in summary_groups if g['group'] in
                      ['ChatDrug', 'S2-mini', 'ChatDrug_single', 'ChatDrug_multi', 'ChatDrug_LogP_QED', 'S2_LogP_QED']],
                      'issues': issues}, ensure_ascii=False))


if __name__ == '__main__':
    main()
