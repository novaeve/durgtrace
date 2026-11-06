from pathlib import Path
import json,hashlib,collections
r=Path('/yimin/zlc/molclaw_type4_20261003')
for p in sorted((r/'evaluation/molclaw').glob('*/result.json')):
 d=json.loads(p.read_text())
 if d.get('status')!='errored':continue
 logs=list((p.parent/'queue').rglob('boltz.log'))
 text='\n'.join(q.read_text(errors='replace') for q in logs)
 original=r/'runs/molclaw'/p.parent.name
 candidates=[q for q in original.rglob('solution.smi') if q.is_file()]
 print(json.dumps({'task':p.parent.name,'msa_retries_exhausted':'Too many failed attempts for the MSA generation request' in text,'colabfold_timeout':'api.colabfold.com' in text and 'timed out' in text,'cuda_oom':'out of memory' in text.lower(),'other_failed_steps':[s['name'] for s in d['steps'] if s['status']=='failed'],'boltz_done':[json.loads(q.read_text()) for q in (p.parent/'queue').rglob('done.json')],'solution_paths':[str(q) for q in candidates]},ensure_ascii=True))
