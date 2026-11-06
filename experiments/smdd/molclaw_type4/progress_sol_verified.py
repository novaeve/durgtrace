from pathlib import Path
import json,collections,time,datetime
r=Path('/yimin/zlc/sol_pi_type4_20261004')
print('CHECK_TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
s=json.loads((r/'scheduler_status.json').read_text());print('SNAPSHOT_AGE',time.time()-s['updated'])
recs=[json.loads(p.read_text()) for p in (r/'runs/solpi').glob('*/record.json')]
print('VERIFIED',len(recs),dict(collections.Counter(d['evaluation'] for d in recs)),'scheduler',s['counts']['solpi'],'blocked',s['blocked']['solpi'])
for item in s['active']['solpi']:
 out=r/'runs/solpi'/item['task'];print('ACTIVE',item['task'],'worker_pid',item['pid'],'process_exists',Path('/proc/'+str(item['pid'])).exists())
 submits=[]
 for p in (out/'tools').glob('*.json'):
  d=json.loads(p.read_text())
  if d['name']=='submit':submits.append({'result':d['result'],'minutes_ago':(time.time()-d['ended'])/60})
 if submits:print('SUBMITS',submits)
 q=out/'guard_events.jsonl'
 if q.exists():
  ds=[json.loads(ln) for ln in q.read_text().splitlines()];print('GUARD_DENIALS',dict(collections.Counter(d['reason'] for d in ds if d['reason'])))
 qs=sorted((out/'api').glob('*.json'))
 if qs:
  d=json.loads(qs[-1].read_text());print('LAST_API',qs[-1].name,'minutes_ago',(time.time()-d.get('ended',d['started']))/60,'http_attempts',d['attempts'][-2:])
  choices=d.get('response',{}).get('choices',[])
  if choices:
   msg=choices[0]['message'];print('LAST_ACTION',str(msg.get('content'))[-500:],[t['function']['name'] for t in msg.get('tool_calls',[])])
