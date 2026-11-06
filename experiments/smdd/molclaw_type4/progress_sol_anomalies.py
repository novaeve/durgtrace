from pathlib import Path
import json
r=Path('/yimin/zlc/sol_pi_type4_20261004')
for p in (r/'runs/solpi').glob('*/record.json'):
 d=json.loads(p.read_text())
 if d['evaluation'] not in ['passed','failed']:
  print('UNSCORED',p.parent.name,d)
  q=p.parent/'result.json'
  if q.exists():print('AGENT',q.read_text()[:1000])
s=json.loads((r/'scheduler_status.json').read_text())
for it in s['active']['solpi']:
 p=r/'runs/solpi'/it['task'];q=p/'boundary_error.json'
 if q.exists():print('BOUNDARY_ERROR',it['task'],json.loads(q.read_text())['error'])
 q=p/'events.jsonl'
 if q.exists():
  tail=q.read_text(errors='replace').splitlines()[-40:]
  for ln in reversed(tail):
   try:d=json.loads(ln)
   except ValueError:continue
   if d.get('type')=='tool_execution_end':
    print('LAST_TOOL_RESULT',it['task'],str(d.get('result',{}))[:700]);break
