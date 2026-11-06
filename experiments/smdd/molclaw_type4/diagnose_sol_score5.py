from pathlib import Path
import json,hashlib,subprocess,shutil,datetime
r=Path('/yimin/zlc/sol_pi_type4_20261004')
print('TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
for p in sorted((r/'runs/solpi').glob('*/record.json')):
 rec=json.loads(p.read_text())
 if rec['evaluation']!='errored':continue
 out=p.parent;result=json.loads((out/'evaluation/result.json').read_text());logs=list((out/'evaluation').rglob('boltz.log'));text='\n'.join(q.read_text(errors='replace') for q in logs)
 print('TASK',out.name,'RECORD',rec,'FAILED_STEPS',[s['name'] for s in result['steps'] if s['status']=='failed'],'ERRORS',[s.get('error') for s in result['steps'] if s['status']=='errored'],'MSA_TIMEOUT','api.colabfold.com' in text and 'timed out' in text,'MSA_RETRIES_EXHAUSTED','Too many failed attempts for the MSA generation request' in text,'CUDA_OOM','out of memory' in text.lower())
 print('FINAL_SUBMISSION',{'exists':(out/'solution.smi').exists(),'sha256':hashlib.sha256((out/'solution.smi').read_bytes()).hexdigest() if (out/'solution.smi').exists() else None})
 for q in logs:
  hits=[ln for ln in q.read_text(errors='replace').splitlines() if 'Exception:' in ln or 'Error:' in ln or 'OutOfMemory' in ln];print('LOG_ERRORS',hits[-3:])
print('SERVICE',subprocess.getoutput('systemctl --user show sol-pi-type4-a100.service -p ActiveState -p MainPID'))
print('DISK_FREE_GIB',round(shutil.disk_usage(r).free/1024**3,2))
print('GPU',subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
for name in ['runtime.py','evaluate.py','gpu_slots.py','smdd_eval_bridge.py']:
 print('SOURCE_HASH',name,hashlib.sha256((r/name).read_bytes()).hexdigest())
