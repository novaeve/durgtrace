"""Compare input tasks and re-score final outputs with both aromatic treatments."""
import collections
import functools
import json
import statistics
from pathlib import Path
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
import rdkit

BASE = Path('/data2/chenfuxin')
ROOT = BASE / 'chatdrug_amplitude_ablation_20261005'
CASES_PATH = BASE / 'chatdrug_generalization_20260920/prepared_full/cases.json'
RDLogger.DisableLog('rdApp.*')


@functools.lru_cache(maxsize=30000)
def value(smiles, prop, kekule=False):
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    if kekule:
        Chem.Kekulize(mol)
    return {'LogP': Descriptors.MolLogP, 'QED': Descriptors.qed,
            'MW': Descriptors.MolWt, 'HA': Descriptors.HeavyAtomCount}[prop](mol)


def main():
    cases = json.loads(CASES_PATH.read_text())
    case_map = {c['id']: c for c in cases}
    inputs = []
    canonical_sets = {}
    for bench in ['ChatDrug', 'S2-mini']:
        for prop in ['LogP', 'QED']:
            selected = [c for c in cases if c['benchmark'] == bench
                        and c['property'] == prop and len(c['objectives']) == 1]
            smiles = sorted({c['smiles'] for c in selected})
            canonical_sets[(bench, prop)] = {Chem.MolToSmiles(Chem.MolFromSmiles(s)) for s in smiles}
            stats = {}
            for name in ['LogP', 'QED', 'MW', 'HA']:
                vals = [value(s, name) for s in smiles]
                stats[name] = {'mean': statistics.mean(vals), 'median': statistics.median(vals),
                               'min': min(vals), 'max': max(vals)}
            inputs.append({'benchmark': bench, 'property': prop, 'rows': len(selected),
                           'unique_inputs': len(smiles), 'directions': dict(collections.Counter(c['direction'] for c in selected)),
                           'prompts': dict(collections.Counter(c['instruction'].replace(c['smiles'], '<SMILES>') for c in selected)),
                           'stats': stats,
                           'kekule_logp_changes': sum(abs(value(s, 'LogP')-value(s, 'LogP', True)) > 1e-12 for s in smiles),
                           'kekule_qed_changes': sum(abs(value(s, 'QED')-value(s, 'QED', True)) > 1e-12 for s in smiles)})
    groups = collections.defaultdict(collections.Counter)
    details = []
    for path in [ROOT / 'rows.json', ROOT / 'additional/rows.json']:
        for row in json.loads(path.read_text()):
            c = case_map[row['id']]
            if c['property'] not in ['LogP', 'QED'] or len(c['objectives']) != 1:
                continue
            prop, direction = c['objectives'][0]
            plain = kekule = False
            if row['complete']:
                original = value(c['smiles'], prop)
                modified = value(row['candidate'], prop)
                plain = modified is not None and (modified-original)*direction > 0
                original_k = value(c['smiles'], prop, True)
                modified_k = value(row['candidate'], prop, True)
                kekule = modified_k is not None and (modified_k-original_k)*direction > 0
            saved = row['direction_only_success']
            assert saved == (kekule if c['benchmark'] == 'ChatDrug' else plain), (row['agent'], row['id'])
            labels = [c['benchmark'], c['benchmark']+'_'+c['direction']]
            if c['benchmark'] == 'ChatDrug':
                labels += [c['benchmark']+'_'+c['constraint']]
            for label in labels:
                g = groups[(row['agent'], label, prop)]
                g['expected'] += 1
                g['saved_success'] += saved
                g['plain_success'] += plain
                g['kekule_success'] += kekule
                g['plain_rescued'] += plain and not saved
                g['plain_lost'] += saved and not plain
            details.append({'agent': row['agent'], 'id': row['id'], 'property': prop,
                            'saved_success': saved, 'plain_success': plain, 'kekule_success': kekule})
    output_groups = []
    for (agent, label, prop), g in sorted(groups.items()):
        d = dict(g)
        d.update(agent=agent, group=label, property=prop)
        for name in ['saved', 'plain', 'kekule']:
            d[name+'_rate'] = d[name+'_success']/d['expected']
        output_groups.append(d)
    report = {'rdkit_version': rdkit.__version__, 'inputs': inputs,
              'canonical_overlap': {prop: len(canonical_sets[('ChatDrug', prop)] & canonical_sets[('S2-mini', prop)]) for prop in ['LogP', 'QED']},
              'groups': output_groups,
              'validation': 'All saved directional scores matched recomputation with each original aromatic treatment.',
              'interpretation_limit': 'Re-scoring fixed outputs measures scoring differences, not effects of changing prompts or feedback during generation.'}
    out = ROOT / 'logp_qed_audit'
    out.mkdir(exist_ok=True)
    (out/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (out/'rows.json').write_text(json.dumps(details, ensure_ascii=False))
    print(json.dumps({'inputs': inputs, 'canonical_overlap': report['canonical_overlap'],
                      'groups': [g for g in output_groups if g['group'] in ['ChatDrug', 'S2-mini']],
                      'validation': report['validation']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
