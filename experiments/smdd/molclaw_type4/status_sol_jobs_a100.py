from pathlib import Path
import json,subprocess,time
r=Path('/yimin/zlc/sol_pi_type4_20261004');mol=Path('/yimin/zlc/molclaw_type4_20261003')
if (r/'scheduler_status.json').exists():print('SOL', (r/'scheduler_status.json').read_text())
for p in (r/'runs/solpi').glob('*'):
 print('TASK',p.name)
 for name in ['record.json','result.json','boundary_error.json','worker_error.log','worker.log','stderr.log','evaluation/result.json','evaluation/container.log']:
  q=p/name
  if q.exists():print(name,q.read_text(errors='replace')[-1600:])
 print('API',len(list((p/'api').glob('*.json'))),'TOOLS',len(list((p/'tools').glob('*.json'))))
 for q in sorted((p/'tools').glob('*.json'))[-2:]:
  d=json.loads(q.read_text());print('TOOL',d['name'],str(d.get('result',''))[:1000])
 for name in ['gpu_slot.json','resource_wait.json','boltz_provenance.json']:
  for q in p.rglob(name):print('LEASE',q.relative_to(p),q.read_text())
 for q in p.rglob('boltz.log'):print('BOLTZ',q.relative_to(p),q.read_text(errors='replace')[-800:])
 ev=p/'events.jsonl'
 if ev.exists():
  for ln in ev.read_text(errors='replace').splitlines()[-3:]:
   try:d=json.loads(ln)
   except ValueError:continue
   if d.get('type')=='message_update':continue
   print('NATIVE',str(d)[:1500])
print('GPU',subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,utilization.gpu','--format=csv,noheader'],text=True))
for n in ['scheduler_status.json','batch_status.json']:
 if (mol/n).exists():
  d=json.loads((mol/n).read_text());print('MOL_STATUS',n,json.dumps({k:v for k,v in d.items() if k not in ['active','blocked','tasks']})[:2000])
