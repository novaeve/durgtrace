from pathlib import Path
import json,collections,time,datetime
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004')
print('CHECK_TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
s=json.loads((r/'scheduler_status.json').read_text());print('SNAPSHOT_AGE',time.time()-s['updated'])
for m in ['deepseek','codex']:
 recs=[(p,json.loads(p.read_text())) for p in (r/'runs'/m).glob('*/record.json')]
 print('VERIFIED',m,'terminal',len(recs),'evaluation',dict(collections.Counter(d['evaluation'] for p,d in recs)),'scheduler',s['counts'][m],'blocked',s['blocked'][m])
 for p,d in recs:
  if d['evaluation'] not in ['passed','failed']:
   print('ANOMALY',m,p.parent.name,d)
   q=p.parent/'result.json'
   if q.exists():print('AGENT_RESULT',q.read_text()[:1500])
   q=p.parent/'workspace/solution.smi';print('SOLUTION_EXISTS',q.exists())
