"""Re-score fixed aligned outputs with S2 LogP/QED calculations; no API calls."""
import ast
import collections
import functools
import hashlib
import json
from pathlib import Path
import statistics
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
import rdkit

ROOT = Path(__file__).resolve().parent
BASE = Path('/data2/chenfuxin')
CHAT = BASE/'chatdrug_generalization_20260920'
METHODS = ['ChatDrug', 'AgentDrug', 'DeepSeek_direct']


@functools.lru_cache(maxsize=30000)
def kekule_value(smiles, prop):
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    Chem.Kekulize(mol)
    return (Descriptors.MolLogP if prop == 'LogP' else Descriptors.qed)(mol)


def main():
    RDLogger.DisableLog('rdApp.*')
    source = CHAT/'upstream/S2-TOMG-Bench/utils/evaluation.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'mol_prop')
    ns = {'Chem': Chem, 'Descriptors': Descriptors}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), ns)
    plain_value = functools.lru_cache(maxsize=30000)(ns['mol_prop'])
    cases = json.loads((CHAT/'prepared_full/cases.json').read_text())
    aligned_cases = {c['id']: c for c in json.loads((ROOT/'cases.json').read_text())}
    groups = collections.defaultdict(collections.Counter)
    rows, digests = [], {}
    for method in METHODS:
        digest = hashlib.sha256()
        for c in cases:
            if c['property'] not in ['LogP', 'QED'] or len(c['objectives']) != 1:
                continue
            prop = c['property']
            direction = c['objectives'][0][1]
            aligned = c['benchmark'] == 'ChatDrug'
            if aligned:
                path = ROOT/'runs'/method/c['id']/'result.json'
                expected_case = aligned_cases[c['id']]
            else:
                historical = BASE/'agentdrug_20260922/runs/full' if method == 'AgentDrug' else CHAT/'runs/deepseek_full'
                path = historical/c['id']/'result.json'
                expected_case = c
            raw = path.read_bytes()
            digest.update(c['id'].encode()+b'\0'+raw+b'\0')
            result = json.loads(raw)
            assert result['case'] == expected_case
            complete = result['status'] == 'complete'
            if aligned:
                assert complete
                stored = result['score_direction_only']
            elif method == 'AgentDrug':
                stored = result.get('score', {})
            else:
                stored = result.get('arms', {}).get('chatdrug' if method == 'ChatDrug' else 'direct', {})
            candidate = stored.get('candidate')
            descriptor = 'logP' if prop == 'LogP' else 'qed'
            before = plain_value(c['smiles'], descriptor)
            after = plain_value(candidate, descriptor) if complete and candidate else None
            harmonized = after is not None and (after-before)*direction > 0
            previous = complete and bool(stored.get('success'))
            if aligned and complete:
                bk = kekule_value(c['smiles'], prop)
                ak = kekule_value(candidate, prop)
                assert previous == bool(ak is not None and (ak-bk)*direction > 0)
            elif complete:
                assert previous == harmonized
            group = 'Aligned_ChatDrug' if aligned else 'Historical_S2'
            g = groups[(method, group, prop)]
            g['expected'] += 1
            g['complete'] += complete
            g['previous_success'] += previous
            g['harmonized_success'] += harmonized
            g['rescued'] += harmonized and not previous
            g['lost'] += previous and not harmonized
            rows.append({'method': method, 'dataset': group, 'property': prop, 'id': c['id'],
                         'candidate': candidate, 'previous_success': previous, 'harmonized_success': harmonized,
                         'plain_input_value': before, 'plain_output_value': after})
        digests[method] = digest.hexdigest()
    output_groups = []
    for (method, dataset, prop), counts in sorted(groups.items()):
        g = dict(counts)
        assert g['expected'] == (800 if dataset == 'Aligned_ChatDrug' else 500)
        if prop == 'QED':
            assert g['rescued'] == 0 and g['lost'] == 0
        g.update(method=method, dataset=dataset, property=prop,
                 previous_rate=g['previous_success']/g['expected'],
                 harmonized_rate=g['harmonized_success']/g['expected'])
        output_groups.append(g)
    report = {'protocol': 'Use original S2 mol_prop directly, without Kekulize, and require strict directional improvement. Re-score stored final outputs; no generation or candidate reselection.',
              'rdkit_version': rdkit.__version__, 's2_properties_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'input_result_digests': digests, 'groups': output_groups,
              'validation': 'Original saved scores reproduced; historical S2 scores unchanged; QED scores unchanged; 800 aligned and 500 S2 cases per property and method.',
              'limits': ['Original online feedback/stopping still used the original Kekulize calculations.',
                         'Datasets use different molecules; aligned run used Bailian deepseek-v4.1-flash, historical S2 used official deepseek-flash.']}
    out = ROOT/'harmonized_evaluation'
    out.mkdir(exist_ok=True)
    (out/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (out/'rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
