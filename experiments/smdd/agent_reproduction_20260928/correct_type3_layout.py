"""Pre-launch correction: retain the original evaluator's Boltz job/file names."""
import hashlib,json,shutil
from pathlib import Path
INSTALL=Path('/data2/chenfuxin/agent_reproduction_20260928')
ROOT=Path('/data2/chenfuxin/liddia_smdd_type3_20261004');source=ROOT/'source'
assert not (ROOT/'smoke').exists() and not (ROOT/'runs').exists()
shutil.copy2(ROOT/'manifest.json',ROOT/'manifest.provision_v1.json')
p=source/'smdd_backends.py';s=p.read_text()
old='def boltz_payload(payload, output, gpu=1, samples=10, seed=42):'
assert s.count(old)==1
s=s.replace(old,"def boltz_payload(payload, output, gpu=1, samples=10, seed=42, job_name='input'):\n    if Path(job_name).name!=job_name or not job_name or job_name in ('.','..'):raise ValueError('Invalid job name')")
s=s.replace("job/'input.yaml'","job/(job_name+'.yaml')")
s=s.replace("job/'out/boltz_results_input/predictions/input/affinity_input.json'", "job/'out'/('boltz_results_'+job_name)/'predictions'/job_name/('affinity_'+job_name+'.json')")
p.write_text(s)
shutil.copy2(INSTALL/'evaluate_liddia_type3.py',source/'evaluate_liddia_type3.py')
manifest=json.loads((ROOT/'manifest.json').read_text())
manifest['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')}
manifest['prelaunch_revision']='Preserve original evaluator Boltz job names; no model or metric change'
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('Corrected and frozen before any inference')
