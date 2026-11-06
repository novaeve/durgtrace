"""Prepare the original 5600+1500 benchmark using the validated native SoL-Pi adapter."""
from pathlib import Path
import collections
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
SOURCE = HOME / 'sol_pi_fourbench_20261005'
CHAT = HOME / 'chatdrug_generalization_20260920'
ORIGINAL = HOME / 'molopt_original_bailian_20261007'
CASE_HASH = '81b3bed3ac18d3befddbd60afea5076b4ebe041226bfe3de0b9f920413066e92'
RUN_HASH = '8f75e568adf796508b9813cedfad6a210639dc46d9b11d0101521da3af5b62cb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new)


assert not (ROOT / 'manifest.json').exists(), 'Do not replace a prepared experiment'
assert sha(ORIGINAL / 'cases.json') == CASE_HASH
assert (ORIGINAL / 'cases.json').read_bytes() == (CHAT / 'prepared_full/cases.json').read_bytes()
assert sha(SOURCE / 'run.py') == RUN_HASH
raw = json.loads((ORIGINAL / 'cases.json').read_text())
assert len(raw) == 7100 and len({case['id'] for case in raw}) == 7100
assert collections.Counter(case['benchmark'] for case in raw) == {'ChatDrug': 5600, 'S2-mini': 1500}
assert collections.Counter(case['property'] for case in raw if case['benchmark'] == 'S2-mini') == {'LogP': 500, 'QED': 500, 'MR': 500}
cases, indexes = [], collections.Counter()
for case in raw:
    row = dict(case)
    bucket = f"{case['task']}_{case['constraint']}" if case['benchmark'] == 'ChatDrug' else f"{case['property']}_{case['direction']}"
    key = (case['benchmark'], bucket)
    row.update(bench=case['benchmark'], bucket=bucket, index=indexes[key], prompt=case['instruction'])
    indexes[key] += 1
    cases.append(row)
assert sum(case['index'] == 0 for case in cases) == 34
(ROOT / 'original_cases.json').write_bytes((ORIGINAL / 'cases.json').read_bytes())
(ROOT / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2))
(ROOT / 'source').mkdir(exist_ok=True)
shutil.copy2(CHAT / 'full_experiment.py', ROOT / 'source/original_full_experiment.py')
text = (SOURCE / 'run.py').read_text()
text = text.replace('fourbench-deepseek', 'mol-edit-deepseek')
text = text.replace('FOURBENCH_BOUNDARY_URL', 'MOLEDIT_BOUNDARY_URL')
text = text.replace('/opt/bridge/fourbench.ts', '/opt/bridge/moledit.ts')
text = replace_once(text, 'WALL_SECONDS, IDLE_SECONDS, WORKERS = 3600, 1800, 2',
                    'WALL_SECONDS, IDLE_SECONDS, WORKERS = 3600, 1800, 8')
text = replace_once(text, "'PATH': str(MOL / 'isolated_env/bin') + ':/usr/local/bin:/usr/bin:/bin',",
                    "'PATH': str(HOME / 'chatdrug_generalization_20260920/venv/bin') + ':/usr/local/bin:/usr/bin:/bin',")
text = replace_once(text, "'PYTHONPATH': str(OLD / 'deps'),", "'PYTHONPATH': '',")
text = replace_once(text, "'--ro-bind', str(ROOT / 'bridge'), '/opt/bridge',",
                    "'--ro-bind', str(ROOT / 'bridge'), '/opt/bridge',\n            '--ro-bind', str(HOME / '.pi/agent/bin/rg'), '/opt/pi-tools/rg',\n            '--ro-bind', str(HOME / '.pi/agent/bin/fd'), '/opt/pi-tools/fd',")
text = replace_once(text, '        shutil.copy2(source, target)',
                    "        target.symlink_to('/opt/pi-tools/' + name)")
start = text.index('def parse(text):')
end = text.index('\n\ndef sandbox(', start)
text = text[:start] + '''def parse(text):
    # Original MolClaw benchmark single-submission parser; no trajectory selection.
    tags = re.findall(r'<answer>\\s*(.*?)\\s*</answer>', text, re.S | re.I)
    if len(tags) != 1:
        return None
    candidate = tags[0].strip()
    return candidate if candidate and not any(c.isspace() for c in candidate) else None
''' + text[end:]
text = replace_once(text, "    query = case['prompt'].replace('<smiles>', '<answer>').replace('</smiles>', '</answer>')",
                    "    query = case['instruction']")
text = replace_once(text, "    selected = cases()\n    if stage == 'pilot':",
                    "    selected = cases()\n    if stage == 'full':\n        groups = [[c for c in selected if c['benchmark'] == name] for name in ['ChatDrug', 'S2-mini']]\n        selected = [group[index] for index in range(max(map(len, groups))) for group in groups if index < len(group)]\n    if stage == 'pilot':")
text = replace_once(text, "        selected = [c for c in selected if c['index'] == 0]",
                    "        selected = [next(c for c in selected if c['benchmark'] == name) for name in ['ChatDrug', 'S2-mini']]")
compile(text, str(ROOT / 'run.py'), 'exec')
(ROOT / 'run.py').write_text(text)
shutil.copy2(SOURCE / 'relay.py', ROOT / 'relay.py')
bridge = (SOURCE / 'bridge/fourbench.ts').read_text().replace('fourbench-deepseek', 'mol-edit-deepseek').replace('FOURBENCH_BOUNDARY_URL', 'MOLEDIT_BOUNDARY_URL')
(ROOT / 'bridge').mkdir(exist_ok=True)
(ROOT / 'bridge/moledit.ts').write_text(bridge)
(ROOT / 'bridge/node_modules').symlink_to('/opt/sol-pi/node_modules', target_is_directory=True)
pins = {CHAT / 'full_experiment.py': '0998f12f5f4da4910606d6c2aca85befe91103775c7b9f64793fea99dbf7375d',
        CHAT / 'pilot.py': '0294a4125863744543545e9de6c7665646f17ba7442c1c4d6926fb856ba52331',
        CHAT / 'deepseek_check.py': 'bc3de4735708ab814b38637aa038b503c7f56abc7745902785e9788fd71d18de'}
assert all(sha(path) == digest for path, digest in pins.items())
manifest = {'method': 'sol-pi', 'counts': {'ChatDrug-MolEdit-28': 5600, 'S2-miniMolOpt': 1500},
            'model': 'deepseek-v4.1-flash', 'temperature': 0, 'enable_thinking': False,
            'reasoning_effort': None, 'workers': 8, 'pilot_cases': 2,
            'key_source': '/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env',
            'case_sha256': CASE_HASH, 'original_case_source': str(ORIGINAL / 'cases.json'),
            'frozen_scorer_dependencies': {str(path): digest for path, digest in pins.items()},
            'protocol': 'original prompts, amplitude/loose/strict thresholds, Kekulize and S2 directional scores; no harmonization',
            'submission': 'one final answer per case; score only after the native episode ends',
            'budget': {'wall_seconds': 3600, 'idle_seconds': 1800, 'upstream_max_tokens': 'omitted; native provider default'},
            'budget_comparison': 'Native harness tools, reasoning context and call counts remain harness differences; not declared equal to ChatDrug/AgentDrug internal caps',
            'execution': 'same validated native SoL-Pi adapter, original benchmark Python/RDKit environment; both datasets interleaved',
            'storage': {'root': str(ROOT), 'shared_immutable_tools': ['rg', 'fd'], 'minimum_free_gib_before_new_case': 20},
            'source_hashes': {str(path.relative_to(ROOT)): sha(path) for path in list(ROOT.glob('*.py')) + list((ROOT / 'bridge').glob('*.ts')) + list((ROOT / 'source').glob('*.py'))},
            'same_models_for_primary_and_reducer': True,
            'all_four_mechanisms': True}
(ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'prepared': True, 'count': 7100, 'pilot': 2, 'original_case_hash': CASE_HASH}))
