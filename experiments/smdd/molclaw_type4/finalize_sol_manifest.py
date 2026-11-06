from pathlib import Path
import json,hashlib
r=Path('/yimin/zlc/sol_pi_type4_20261004');p=r/'manifest.json';d=json.loads(p.read_text())
d['official_agent_config']['model']='openai/deepseek-v4.1-flash'
d['deployment_sha256']={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list(r.glob('*.py'))+list((r/'bridge').glob('*')) if p.is_file()}
p.write_text(json.dumps(d,indent=2));print('MANIFEST_MODEL_AND_HASHES_FINALIZED')
