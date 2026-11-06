from pathlib import Path
import json,time,hashlib,subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004');d=json.loads((r/'repair_current.json').read_text());archive=Path(d['archive'])
print('LONG_HTTP_TEST',(r/'transport_fix_test.log').read_text());print('SCHEDULER',(r/'scheduler_status.json').read_text())
for tid in d['tasks']:
 out=r/'runs/solpi'/tid
 q=out/'boundary_error.json'
 if q.exists() and q.stat().st_mtime<d['time']:
  q.rename(archive/'task_before'/tid/'boundary_error_before_fix.json')
 print('TASK',tid)
 for n in ['result.json','record.json','budget_state.json','evaluation/result.json']:
  q=out/n
  if q.exists():print(n,q.read_text()[:1300])
 state=json.loads((out/'resume_state.json').read_text());apis=sorted((out/'api').glob('*.json'));new=[p for p in apis if int(p.stem)>state['calls']]
 print('NEW_API_FILES',[p.name for p in new])
 for p in new[-1:]:
  v=json.loads(p.read_text());print('MODEL_SETTINGS',{k:v['request'][k] for k in ['model','enable_thinking','temperature']},'response_model',v.get('response',{}).get('model'))
 lasttools=[p for p in (out/'tools').glob('*.json') if int(p.stem)>state['tool_calls']]
 for p in sorted(lasttools)[-2:]:
  v=json.loads(p.read_text());print('NEW_TOOL',v['name'],'duration',round(v['ended']-v['started'],1),'result',str(v['result'])[:400])
 q=out/'stderr.log'
 if q.exists() and q.stat().st_size:print('STDERR',q.read_text()[-1000:])
print('MOL_PID',subprocess.check_output(['systemctl','--user','show','molclaw-type4-a100.service','-p','MainPID','--value'],text=True).strip())
