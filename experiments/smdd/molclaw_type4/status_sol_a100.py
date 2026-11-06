from pathlib import Path
import json,subprocess,time
r=Path('/yimin/zlc/sol_pi_type4_20261004')
for name in ['install.log','source_validation.log','preflight.log']:
 p=r/name
 if p.exists():print('LOG',name,p.read_text(errors='replace')[-2300:])
for name in ['source_validation.json','preflight/result.json','scheduler_status.json']:
 p=r/name
 if p.exists():
  d=json.loads(p.read_text())
  if name.endswith('result.json'):d.pop('runtime_tool_schemas',None)
  print('STATUS',name,json.dumps(d)[:2800])
for p in r.glob('preflight/solpi/*/stderr.log'):print('NATIVE_STDERR',p.read_text()[-1800:])
for p in r.glob('preflight/solpi/*/result.json'):print('NATIVE_RESULT',p.read_text())
print('GPU',subprocess.getoutput('nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader'))
