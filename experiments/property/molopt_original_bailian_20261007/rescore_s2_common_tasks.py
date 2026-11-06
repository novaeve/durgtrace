"""Apply S2 MolOpt scoring to both datasets' saved original-prompt outputs."""
import ast
import collections
import functools
import hashlib
import importlib.util
import json
from pathlib import Path
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
import rdkit

ROOT = Path(__file__).resolve().parent
CHAT = Path('/data2/chenfuxin/chatdrug_generalization_20260920')
METHODS = ['DeepSeek_direct', 'ChatDrug', 'AgentDrug']


def main():
    RDLogger.DisableLog('rdApp.*')
    source = CHAT/'upstream/S2-TOMG-Bench/utils/evaluation.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'mol_prop')
    namespace = {'Chem': Chem, 'Descriptors': Descriptors}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
    mol_prop = functools.lru_cache(maxsize=30000)(namespace['mol_prop'])
    original_eval = CHAT/'upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py'
    spec = importlib.util.spec_from_file_location('original_chatdrug_eval', original_eval)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    cases = [c for c in json.loads((ROOT/'cases.json').read_text())
             if c['property'] in ['LogP', 'QED'] and len(c['objectives']) == 1]
    assert len(cases) == 2600
    groups = collections.defaultdict(collections.Counter)
    rows, digests = [], {}
    for method in METHODS:
        digest = hashlib.sha256()
        for case in cases:
            path = ROOT/'runs'/method/case['id']/'result.json'
            raw = path.read_bytes()
            digest.update(case['id'].encode()+b'\0'+raw+b'\0')
            result = json.loads(raw)
            assert result['case'] == case
            complete = result['status'] == 'complete'
            candidate = result.get('candidate')
            old_success = complete and result['score']['success']
            descriptor = 'logP' if case['property'] == 'LogP' else 'qed'
            direction = case['objectives'][0][1]
            if case['benchmark'] == 'S2-mini':
                lower = 'lower' in case['instruction'] or 'decrease' in case['instruction']
                assert direction == (-1 if lower else 1)
            valid = complete and isinstance(candidate, str) and bool(mol_prop(candidate, 'validity'))
            before = mol_prop(case['smiles'], descriptor)
            after = mol_prop(candidate, descriptor) if valid else None
            s2_success = valid and (after < before if direction == -1 else after > before)
            if complete and case['benchmark'] == 'ChatDrug':
                _, _, original_answer = original.evaluate_molecule(case['smiles'], candidate, case['task'], case['thresholds'])
                assert old_success == (original_answer != -1 and bool(original_answer))
            if case['benchmark'] == 'S2-mini':
                assert s2_success == old_success
            group = groups[(method, case['benchmark'], case['property'])]
            group['expected'] += 1
            group['complete'] += complete
            group['valid'] += valid
            group['original_success'] += old_success
            group['s2_success'] += s2_success
            group['rescued'] += s2_success and not old_success
            group['lost'] += old_success and not s2_success
            rows.append({'method': method, 'benchmark': case['benchmark'], 'property': case['property'],
                         'id': case['id'], 'original_setting': case['constraint'], 'candidate': candidate,
                         'direction': direction, 'original_success': old_success, 's2_success': s2_success,
                         'input_property': before, 'output_property': after, 'valid': valid})
        digests[method] = digest.hexdigest()
    output = []
    for (method, benchmark, prop), counts in sorted(groups.items()):
        g = dict(counts)
        assert g['expected'] == (800 if benchmark == 'ChatDrug' else 500)
        g.update(method=method, benchmark=benchmark, property=prop,
                 original_rate=g['original_success']/g['expected'],
                 s2_rate=g['s2_success']/g['expected'])
        output.append(g)
    report = {
        'model': 'deepseek-v4.1-flash', 'provider': 'Alibaba Bailian for both datasets and all methods',
        'protocol': 'Official S2 mol_prop and strict directional comparison; no Kekulize, no amplitude or similarity cutoff; invalid/missing/error final outputs fail.',
        'direction_mapping': 'Retain original task ground truth: ChatDrug task 101 lowers LogP, 102 raises LogP, 103 raises QED, 104 lowers QED; S2 instruction parsing checked against saved task directions.',
        'generation': 'Saved original-prompt baseline outputs only; no new model calls or candidate reselection.',
        'source_result_digests': digests, 'rdkit_version': rdkit.__version__,
        's2_property_code_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'groups': output,
        'validation': 'Original ChatDrug outcomes reproduced; S2 outcomes unchanged; 800 ChatDrug and 500 S2 cases per property/method; 7800 saved outputs checked.',
        'limits': 'Only final evaluation unified. Original task wording, input molecules, and online agent feedback/stopping remain unchanged.'}
    destination = ROOT/'s2_common_task_evaluation'
    destination.mkdir(exist_ok=True)
    (destination/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (destination/'rows.json').write_text(json.dumps(rows, ensure_ascii=False))
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
