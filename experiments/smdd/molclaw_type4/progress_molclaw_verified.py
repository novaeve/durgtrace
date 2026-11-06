from pathlib import Path
import json,collections,time,datetime,subprocess
r=Path('/yimin/zlc/molclaw_type4_20261003')
print('CHECK_TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
s=json.loads((r/'status.json').read_text());print('SCHEDULER',json.dumps(s),'SNAPSHOT_AGE',time.time()-s['time'])
ds=[(p,json.loads(p.read_text())) for p in (r/'evaluation/molclaw').glob('*/result.json')]
print('VERIFIED',len(ds),'RESULT_COUNTS',dict(collections.Counter(d.get('status','missing_status') for p,d in ds)))
for p,d in ds:
 if d.get('status') not in ['passed','failed']:print('ANOMALY',p.parent.name,json.dumps(d)[:1200])
for tid in s['active']:
 p=r/'worker_state'/f'{tid}.json';d=json.loads(p.read_text()) if p.exists() else {};print('WORKER',tid,d,'alive',Path('/proc/'+str(d.get('pid','-1'))).exists())
 q=r/'worker_logs'/f'{tid}.log'
 if q.exists():print('WORKER_LOG',tid,q.read_text(errors='replace')[-650:])
print('SERVICE',subprocess.getoutput('systemctl --user show molclaw-type4-a100.service -p ActiveState -p SubState -p MainPID -p NRestarts'))
print('GPU',subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,utilization.gpu','--format=csv,noheader'],text=True))
