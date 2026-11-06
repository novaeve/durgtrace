from pathlib import Path
import json,collections,time,hashlib,subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004');s=json.loads((r/'scheduler_status.json').read_text())
ids=[it['task'] for it in s['active']['solpi']]+['smdd_004_ACE_4','smdd_004_ACE_15','smdd_004_ACE_20']
print('COUNTS',s['counts']);print('REMOTE_BRIDGE',(r/'bridge/smdd.ts').read_text())
for tid in dict.fromkeys(ids):
 out=r/'runs/solpi'/tid
 if not out.exists():continue
 print('\nTASK',tid)
 for name in ['result.json','boundary_error.json','stderr.log','process.json']:
  q=out/name
  if q.exists():print(name,q.read_text(errors='replace')[-1600:])
 tools=[]
 for q in sorted((out/'tools').glob('*.json')):
  d=json.loads(q.read_text());tools.append(d)
 print('TOOLS',dict(collections.Counter(d['name'] for d in tools)))
 for d in tools:
  if d['name']=='submit' or ('error' in str(d['result']).lower() or 'failed' in str(d['result']).lower()):print('TOOL_DETAIL',d['name'],'duration',round(d['ended']-d['started'],1),'ended',d['ended'],'result',str(d['result'])[:650])
 q=out/'events.jsonl';errors=[];calls=[]
 if q.exists():
  for ln in q.read_text(errors='replace').splitlines():
   try:d=json.loads(ln)
   except ValueError:continue
   if d.get('type')=='tool_execution_end' and (d.get('isError') or 'fetch failed' in str(d.get('result',''))):errors.append(d)
   if d.get('type')=='tool_execution_start':calls.append(d)
 print('NATIVE_ERRORS',len(errors))
 for d in errors[-8:]:print('ERROR',json.dumps(d)[:1300])
 for d in calls[-5:]:print('LAST_CALL',json.dumps(d)[:600])
 for q in sorted((out/'api').glob('*.json'))[-2:]:
  d=json.loads(q.read_text());print('API_TIME',q.name,d['started'],d.get('ended'));print('LAST_RESPONSE',str(d.get('response',{}).get('choices',[]))[-1100:])
 print('GPU_REQUESTS',sum(1 for _ in out.rglob('boltz_provenance.json')))
pi=r/'SoL-Pi/node_modules/@earendil-works/pi-coding-agent'
print('PI_TOOL_SIGNATURE_SEARCH',subprocess.getoutput("rg -n 'execute:|execute\\(|AbortSignal|timeout' "+str(pi/'dist/core/extensions/types.d.ts')+" | head -50"))
