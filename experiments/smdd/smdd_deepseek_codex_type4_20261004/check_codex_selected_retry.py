from pathlib import Path
import json,time,hashlib,datetime
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');batch=r/'codex_selected_retry_20261007'
manifest=json.loads((batch/'manifest.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
print('TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
launch=json.loads((batch/'detached_launch.json').read_text());print('DRIVER_ALIVE',Path('/proc',str(launch['pid'])).exists())
print('STATUS',(batch/'status.json').read_text())
print('DRIVER_LOG',(batch/'driver.log').read_text(errors='replace')[-1800:])
for tid,meta in manifest['tasks'].items():
 q=batch/'logs'/f'{tid}.log';print('TASK_LOG',tid,q.read_text(errors='replace')[-1600:] if q.exists() else None)
 out=batch/'runs/codex'/tid
 if not out.exists():out=r/'runs/codex'/tid
 api=sorted((out/'api').glob('*.json'));tools=list((out/'tools').glob('*.json'))
 print('PROGRESS',tid,'api_receipts',len(api),'tool_receipts',len(tools),'has_solution',(out/'solution.smi').exists())
 if api:
  req=json.loads(api[-1].read_text()).get('request',{});print('MODEL',req.get('model'),'THINKING',req.get('enable_thinking'))
 for p in (out/'evaluation').rglob('boltz.log'):
  print('SCORING',tid,p.read_text(errors='replace')[-950:])
 for p in out.rglob('resource_wait.json'):
  if time.time()-p.stat().st_mtime<90:print('RESOURCE_WAIT',tid,p.read_text())
untouched={p:h for p,h in manifest['all_terminal_hashes'].items() if Path(p).parent.name not in manifest['tasks'] or '/runs/deepseek/' in '/'+p}
print('NONSELECTED_UNCHANGED',all(sha(r/p)==h for p,h in untouched.items()))
print('SOURCES_UNCHANGED',all(sha(r/name)==h for name,h in manifest['source_hashes'].items()))
completion=batch/'completion.json'
if completion.exists():print('COMPLETION',completion.read_text())
