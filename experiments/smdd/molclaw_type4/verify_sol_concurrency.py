from pathlib import Path
import json,subprocess,time,datetime,os
r=Path('/yimin/zlc/sol_pi_type4_20261004')
s=json.loads((r/'scheduler_status.json').read_text())
print('TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
print('WIDTH',s['concurrency_per_method'],'COUNTS',s['counts'],'BLOCKED',s['blocked'],'SNAPSHOT_AGE',time.time()-s['updated'])
for item in s['active']['solpi']:
 p=r/'runs/solpi'/item['task'];api=sorted((p/'api').glob('*.json'));tools=sorted((p/'tools').glob('*.json'))
 last=json.loads(api[-1].read_text()) if api else {}
 print('WORKER',item['task'],'alive',Path('/proc',str(item['pid'])).exists(),'api_calls',len(api),'tool_calls',len(tools),'last_api_minutes_ago',round((time.time()-last.get('ended',last.get('started',time.time())))/60,2))
 if api:
  req=last.get('request',{});print('MODEL',req.get('model'),'THINKING',req.get('enable_thinking'))
 for path in p.rglob('resource_wait.json'):
  if time.time()-path.stat().st_mtime<90:print('QUEUE',item['task'],path.read_text())
print('SERVICE',subprocess.getoutput('systemctl --user show sol-pi-type4-a100.service -p MainPID -p ActiveState -p NRestarts'))
print('GPU',subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],text=True))
rows=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader'],text=True)
print('APPS',rows)
for row in rows.splitlines():
 pid=row.split(',')[1].strip()
 try:args=Path('/proc',pid,'cmdline').read_bytes().decode().split(chr(0))
 except (OSError,UnicodeError):continue
 paths=[arg for arg in args if '/yimin/zlc/sol_pi_type4_20261004/' in arg and (arg.endswith('.yaml') or arg.endswith('.py'))]
 print('GPU_PROCESS',pid,'SOL_PATHS',paths)
data={'time':time.time(),'status':s,'gpu':rows}
(r/'repairs'/'concurrency_last_verification.json').write_text(json.dumps(data,indent=2))
