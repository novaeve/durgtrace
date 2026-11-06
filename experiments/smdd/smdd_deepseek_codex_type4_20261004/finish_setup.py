from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
local=Path(__file__).resolve().parent;r='/data2/chenfuxin/smdd_deepseek_codex_type4_20261004'
c=manage.connect('gpu');s=c.open_sftp()
for name in ['README.md','gpu_slots.py']:
 if name.endswith('.py'):compile((local/name).read_text(),name,'exec')
 s.put(str(local/name),r+'/'+name)
manage.execute(c,"""from pathlib import Path
import json,hashlib,subprocess,time
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');p=r/'manifest.json';d=json.loads(p.read_text());d['hashes']['gpu_slots.py']=hashlib.sha256((r/'gpu_slots.py').read_bytes()).hexdigest();p.write_text(json.dumps(d,indent=2))
state=json.loads((r/'scheduler_status.json').read_text());assert Path('/proc',str(state['pid'])).exists();assert time.time()-state['updated']<30
print('ACTIVE',json.dumps(state['counts']))
for method in ['deepseek','codex']:
 out=r/'runs'/method/'smdd_004_A2A_Adenosine_0'
 apis=sorted((out/'api').glob('*.json'));print('API',method,'calls_logged',len(apis))
 if apis:
  data=json.loads(apis[-1].read_text());print('ACTUAL_MODEL_SETTINGS',method,{k:data['request'].get(k) for k in ['model','enable_thinking','temperature','reasoning_effort']},'response_model',data.get('response',{}).get('model'))
 for p in out.glob('tools/*.json'):
  data=json.loads(p.read_text());print('CODEX_TOOL',data['name'],'result',data['result'][:180])
 for p in out.glob('workspace/boltz_results/*/boltz_provenance.json'):
  data=json.loads(p.read_text());print('BOLTZ',method,'gpu',data['gpu'])
 if (out/'record.json').exists():print('RECORD',method,(out/'record.json').read_text())
print(subprocess.getoutput('nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader'))
""");s.close();c.close()
