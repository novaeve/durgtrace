from pathlib import Path
import json,collections,time
r=Path('/yimin/zlc/sol_pi_type4_20261004');errors=[]
for p in (r/'runs/solpi').glob('*/evaluation/result.json'):
 d=json.loads(p.read_text())
 if d.get('status')=='errored':
  row={'task':p.parent.parent.name,'errors':[{'step':x.get('name'),'error':x.get('error')} for x in d.get('steps',[]) if x.get('status')=='errored']};errors.append(row);print('SOL_SCORE_ERROR',json.dumps(row))
out=r/'runs/solpi/smdd_004_Androgen_Receptor_3'
if (out/'result.json').exists():
 d=json.loads((out/'result.json').read_text());s=json.loads((out/'submission.json').read_text());print('LATEST_SUBMISSION_EXIT',{'submitted':d['submitted'],'agent_status':d['status'],'seconds_after_accept':d['ended']-s['accepted'],'evaluation_pending':not (out/'evaluation/result.json').exists()})
for name in ['solpi']:
 s=json.loads((r/'scheduler_status.json').read_text());recent_errors=[]
 for it in s['active'][name]:
  p=r/'runs'/name/it['task']/'boundary_error.json'
  if p.exists():recent_errors.append({'task':it['task'],'error':json.loads(p.read_text())['error']})
 print('ACTIVE_BOUNDARY_ERRORS',recent_errors)
