from pathlib import Path
import hashlib
import json
import shutil
import sys
import subprocess
import yaml

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
BASE2 = HOME / 'smdd_type2_transfer_20260929'
BASE3 = HOME / 'smdd_type3_transfer_20260930'
SOL4 = HOME / 'sol_pi_type4_20261004'
CODEX2 = HOME / 'smdd_codex_type2_bailian_20260929'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not (ROOT / 'manifest.json').exists(), 'Do not overwrite a prepared experiment'
(ROOT / 'source').mkdir(exist_ok=True)
for source, destination in [(SOL4 / 'runtime.py', ROOT / 'runtime.py'),
                            (SOL4 / 'gpu_slots.py', ROOT / 'gpu_slots.py'),
                            (BASE2 / 'runtime.py', ROOT / 'source/type2_transport.py'),
                            (BASE3 / 'runtime.py', ROOT / 'source/type3_transport.py'),
                            (BASE2 / 'pharmacophore_3d.py', ROOT / 'source/pharmacophore_3d.py'),
                            (BASE3 / 'evaluate.py', ROOT / 'source/type3_evaluate.py')]:
    shutil.copy2(source, destination)
(ROOT / 'upstream').symlink_to(BASE3 / 'upstream', target_is_directory=True)
(ROOT / 'bridge/node_modules').symlink_to('/opt/sol-pi/node_modules', target_is_directory=True)
sys.path.insert(0, str(ROOT / 'upstream'))
from agent_harness.obfuscate import obfuscate_task
from agent_harness.prompts import TOOL_SCHEMAS
(ROOT / 'bridge/tool_schemas.json').write_text(json.dumps(TOOL_SCHEMAS, indent=2))
public2 = json.loads((CODEX2 / 'public_tasks.json').read_text())
assert len(public2) == 25 and len({x['task_id'] for x in public2}) == 25
ids3 = (BASE3 / 'task_list.txt').read_text().split()
assert len(ids3) == 52 and len(set(ids3)) == 52
inputs = {}
for kind, base, ids in [('type2', BASE2, [x['task_id'] for x in public2]), ('type3', BASE3, ids3)]:
    root = ROOT / kind
    root.mkdir()
    (root / 'public_inputs').mkdir()
    (root / 'tasks').symlink_to(base / 'tasks', target_is_directory=True)
    (root / 'upstream').symlink_to(ROOT / 'upstream', target_is_directory=True)
    (root / 'eval_bridge.py').symlink_to(BASE3 / 'eval_bridge.py')
    cases = []
    expected = {'receptor.pdb'} if kind == 'type2' else {'complex.pdb', 'reference.sdf'}
    for index, tid in enumerate(ids):
        task = yaml.safe_load((base / 'tasks' / tid / 'task.yaml').read_text())
        public = root / 'public_inputs' / tid
        public.mkdir()
        if kind == 'type2':
            existing = CODEX2 / 'public_inputs' / tid
            assert {p.name for p in existing.iterdir()} == expected
            assert task['description'] == public2[index]['description']
            for p in existing.iterdir():
                shutil.copy2(p, public / p.name)
        else:
            generated = Path(obfuscate_task(str(base / 'tasks' / tid), f'task_{index:03d}'))
            assert {p.name for p in generated.iterdir()} == expected
            for p in generated.iterdir():
                shutil.copy2(p, public / p.name)
        hashes = {p.name: sha(p) for p in public.iterdir()}
        if kind == 'type3':
            previous = HOME / 'smdd_type3_harness_20261001/runs/codex' / tid / 'started.json'
            if previous.exists():
                assert hashes == json.loads(previous.read_text())['public_hashes'], tid
        cases.append({'id': tid, 'index': index, 'description': task['description'], 'public_hashes': hashes})
    (root / 'public_cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2))
    inputs[kind] = {'task_count': len(cases), 'ids': ids, 'case_sha256': sha(root / 'public_cases.json')}
source_files = [BASE2 / 'runtime.py', BASE2 / 'pharmacophore_3d.py', BASE3 / 'runtime.py',
                BASE3 / 'evaluate.py', BASE3 / 'eval_bridge.py', SOL4 / 'runtime.py', SOL4 / 'gpu_slots.py']
for folder in [BASE2 / 'agent_harness', BASE3 / 'upstream/agent_harness', SOL4 / 'upstream/agent_harness']:
    for name in ('tools.py', 'config.py', 'prompts.py', 'obfuscate.py'):
        source_files.append(folder / name)
        assert sha(folder / name) == sha(BASE2 / 'agent_harness' / name)
manifest = {'method': 'sol-pi', 'model': 'deepseek-v4.1-flash', 'temperature': 1,
            'type2': {**inputs['type2'], 'enable_thinking': False, 'reasoning_effort': None, 'workers': 2},
            'type3': {**inputs['type3'], 'enable_thinking': True, 'reasoning_effort': 'high', 'workers': 1},
            'credential_source': '/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env',
            'max_calls': 100, 'cumulative_token_budget': 10000000, 'boltz_budget': 8, 'admet_budget': 15,
            'seed': 42, 'prediction_samples': 10, 'max_parallel_samples': 1,
            'gpu_admission': 'reuse current shared leases; free >=28000 MiB; do not interrupt other jobs',
            'wall_seconds': {'type2': 3600, 'type3': 86400},
            'source_hashes': {str(p): sha(p) for p in source_files},
            'experiment_hashes': {str(p.relative_to(ROOT)): sha(p) for p in list(ROOT.glob('*.py')) + list((ROOT / 'bridge').glob('*')) if p.is_file()},
            'pi_version': json.loads((HOME / 'SoL-Pi/node_modules/@earendil-works/pi-coding-agent/package.json').read_text())['version'],
            'sol_pi_commit': subprocess.check_output(['git', '-C', str(HOME / 'SoL-Pi'), 'rev-parse', 'HEAD'], text=True).strip(),
            'isolated_inputs': 'only receptor.pdb (type2), or complex.pdb and reference.sdf (type3)',
            'adaptation': 'common original SMDD scientific tools; native file tools and guarded file-I/O fusion; scientific Python runs only in existing evaluator rootfs, with no network; original Type2 baseline used CPU Docker transport whereas this uses the existing local rootfs'}
(ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
print(json.dumps({'prepared': True, 'type2': 25, 'type3': 52, 'source_tools_identical': True}))
