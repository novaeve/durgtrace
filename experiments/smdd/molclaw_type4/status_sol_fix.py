from pathlib import Path
import json,subprocess,time
r=Path('/yimin/zlc/sol_pi_type4_20261004')
for name in ['transport_fix_test.log','repair_fix_test.log','repair_tests/result.json']:
 p=r/name
 if p.exists():print(name,p.read_text()[-2300:])
for p in (r/'preflight/solpi').glob('*/process.json'):
 out=p.parent
 if (out/'submission.json').exists():
  print('NATIVE_SUBMISSION',out.name,(out/'submission.json').read_text())
  if (out/'stderr.log').exists():print('NATIVE_STDERR',(out/'stderr.log').read_text()[-1500:])
  if (out/'result.json').exists():print('NATIVE_RESULT',(out/'result.json').read_text())
out=r/'runs/solpi/smdd_004_ACE_4';accepted=[json.loads(p.read_text()) for p in (out/'tools').glob('*.json') if json.loads(p.read_text()).get('name')=='submit']
print('ORIGINAL_SOLUTION',{'mtime':(out/'workspace/solution.smi').stat().st_mtime,'accept_time':accepted[0]['ended'],'content':(out/'workspace/solution.smi').read_text()})
print('MOL_SERVICE',subprocess.getoutput('systemctl --user show molclaw-type4-a100.service -p ActiveState -p MainPID -p NRestarts'))
