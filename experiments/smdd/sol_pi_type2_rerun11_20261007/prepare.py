"""Freeze exactly the eleven timed-out Type2 cases into a fresh experiment."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
SOURCE = Path.home() / 'sol_pi_smdd_type2_type3_20261006'
EXPECTED_RUN_SHA = '54c936c54f2578a0058016d5c3eaa48e6946bc4d91dd28c598d3882e151129ff'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not (ROOT / 'manifest.json').exists(), 'Do not overwrite a prepared rerun'
assert sha(SOURCE / 'run.py') == EXPECTED_RUN_SHA
originals = {p.parent.name: json.loads(p.read_text()) for p in (SOURCE / 'type2/runs/solpi').glob('*/result.json')}
ids = {tid for tid, row in originals.items() if row['status'] == 'timeout'}
assert len(originals) == 25 and len(ids) == 11
cases = [case for case in json.loads((SOURCE / 'type2/public_cases.json').read_text()) if case['id'] in ids]
assert len(cases) == 11
files = ['run.py', 'runtime.py', 'gpu_slots.py', 'api_factory.py', 'preflight.py',
         'score_all.py', 'test_policy.py', 'source/type2_transport.py',
         'source/pharmacophore_3d.py', 'bridge/smdd.ts', 'bridge/tool_schemas.json']
for name in files:
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / name, target)
(ROOT / 'upstream').symlink_to(SOURCE / 'upstream', target_is_directory=True)
(ROOT / 'bridge/node_modules').symlink_to('/opt/sol-pi/node_modules', target_is_directory=True)
folder = ROOT / 'type2'
folder.mkdir()
(folder / 'tasks').symlink_to(SOURCE / 'type2/tasks', target_is_directory=True)
(folder / 'public_inputs').mkdir()
for case in cases:
    destination = folder / 'public_inputs' / case['id']
    destination.mkdir()
    for name, digest in case['public_hashes'].items():
        source = SOURCE / 'type2/public_inputs' / case['id'] / name
        assert sha(source) == digest
        shutil.copy2(source, destination / name)
(folder / 'public_cases.json').write_text(json.dumps(cases, indent=2))
original_files = list((SOURCE / 'type2/runs/solpi').glob('*/result.json'))
original_files += list((SOURCE / 'type2/evaluation/solpi').glob('*/result.json'))
original_files += [SOURCE / 'type2/evaluation/summary.json']
manifest = {'source': str(SOURCE), 'method': 'sol-pi', 'benchmark': 'SMDD-type2',
            'task_count': 11, 'task_ids': [case['id'] for case in cases], 'workers': 2,
            'model': 'deepseek-v4.1-flash', 'temperature': 1, 'enable_thinking': False,
            'reasoning_effort': None, 'max_calls': 100, 'cumulative_token_budget': 10000000,
            'boltz_budget': 8, 'admet_budget': 15, 'seed': 42, 'wall_seconds': 3600,
            'credential_source': '/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env',
            'source_hashes': {name: sha(SOURCE / name) for name in files},
            'original_result_hashes': {str(path): sha(path) for path in original_files},
            'selection': 'all eleven timeout cases requested by user; three provider-limit cases excluded',
            'result_policy': 'use latest rerun for selected cases irrespective of quality; no best-of selection',
            'deployment_change': 'one process session per task; terminate only its process group after exit, including residual GPU children; GPU/disk admission before the original task clock starts',
            'trial_policy': 'new workspace, new native session, same original public prompt/input/settings/tools/metric'}
(ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'prepared': True, 'task_ids': manifest['task_ids'], 'count': 11}))
