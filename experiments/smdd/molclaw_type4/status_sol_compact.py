from pathlib import Path
import json,subprocess,time
r=Path('/yimin/zlc/sol_pi_type4_20261004');s=json.loads((r/'scheduler_status.json').read_text())
print('STATE',s['state'],'COUNTS',s['counts'],'BLOCKED',s['blocked'])
for item in s['active']['solpi']:
 p=r/'runs/solpi'/item['task'];print('ACTIVE',item['task'],'age_sec',int(time.time()-item.get('started',time.time())),'api',len(list((p/'api').glob('*.json'))),'tools',len(list((p/'tools').glob('*.json'))))
 for name in ['result.json','record.json','boundary_error.json','evaluation/result.json']:
  q=p/name
  if q.exists():print(name,q.read_text()[:1600])
 for q in p.rglob('resource_wait.json'):print('WAIT',str(q.relative_to(p)),q.read_text())
 for q in p.rglob('boltz_provenance.json'):print('GPU',str(q.relative_to(p)),json.loads(q.read_text())['gpu'])
 for q in p.rglob('boltz.log'):print('BOLTZ',str(q.relative_to(p)),q.read_text(errors='replace')[-600:])
 if (p/'stderr.log').exists() and (p/'stderr.log').stat().st_size:print('STDERR',(p/'stderr.log').read_text()[-1000:])
print('GPU_USAGE',subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,utilization.gpu','--format=csv,noheader'],text=True))
print('GPU_PROCESSES',subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader'],text=True))
print('SERVICE',subprocess.getoutput('systemctl --user show sol-pi-type4-a100.service molclaw-type4-a100.service -p Id -p ActiveState -p MainPID -p NRestarts'))
