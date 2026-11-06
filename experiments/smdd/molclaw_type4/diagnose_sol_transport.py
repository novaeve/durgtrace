from pathlib import Path
import json,time,collections,subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004');s=json.loads((r/'scheduler_status.json').read_text())
for tid in dict.fromkeys([i['task'] for i in s['active']['solpi']]+['smdd_004_ACE_4','smdd_004_ACE_15','smdd_004_ACE_20']):
 out=r/'runs/solpi'/tid
 if not out.exists():continue
 events=[]
 for ln in (out/'events.jsonl').read_text(errors='replace').splitlines():
  try:events.append(json.loads(ln))
  except ValueError:continue
 starts={};results={};errors=[]
 for d in events:
  if d['type']=='tool_execution_start':starts[d['toolCallId']]=d
  if d['type']=='message_end' and d.get('message',{}).get('role')=='toolResult':results[d['message'].get('toolCallId')]=d['message']
  if d['type']=='tool_execution_end' and (d.get('isError') or 'fetch failed' in str(d.get('result',''))):errors.append(d)
 api={};seq=[]
 for q in sorted((out/'api').glob('*.json')):
  d=json.loads(q.read_text());seq.append(d)
  for c in d.get('response',{}).get('choices',[]):
   for call in c['message'].get('tool_calls') or []:api[call['id']]=d
 print('TASK',tid,'ERRORS',dict(collections.Counter(str(d.get('result',{}).get('content')) for d in errors)))
 for e in [d for d in errors if d.get('toolName') in ['python','predict_boltz','submit','predict_admet']][:6]:
  call=e['toolCallId'];a=api.get(call,{});m=results.get(call,{})
  start=a.get('ended');end=m.get('timestamp');end=end/1000 if end else None
  follow=next((x['started'] for x in seq if start and x['started']>start),None)
  print('FIRST_FAILURE',e.get('toolName'),'api_end',start,'msg_timestamp',end,'result_elapsed',round(end-start,2) if start and end else None,'next_api_elapsed',round(follow-start,2) if start and follow else None,'result',str(e.get('result'))[:200])
 for q in sorted((out/'tools').glob('*.json')):
  d=json.loads(q.read_text())
  if d['name'] in ['predict_boltz','submit']:print('HOST_DISPATCH',q.name,d['name'],'start',d['started'],'end',d['ended'],'duration',round(d['ended']-d['started'],1),'result',str(d['result'])[:250])
 proc=json.loads((out/'process.json').read_text());pid=proc['pid']
 env=Path(f'/proc/{pid}/environ')
 if env.exists():print('NATIVE_PID',pid,'PUBLIC_BOUNDARY',[v for v in env.read_bytes().decode().split(chr(0)) if v.startswith('SMDD_BOUNDARY_URL=')])
typ=r/'SoL-Pi/node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/types.d.ts'
lines=typ.read_text().splitlines()
for i,line in enumerate(lines):
 if 'execute:' in line or 'execute(' in line:print('PI_EXECUTE_SIGNATURE','\n'.join(lines[max(0,i-3):i+12]))
code="const s=process.binding('natives')['internal/deps/undici/undici']; for(const term of ['headersTimeout == null','headersTimeout ??','headersTimeout:','bodyTimeout == null']) {const i=s.indexOf(term); console.log(term,i,s.slice(Math.max(0,i-100),i+350));}"
print('UNDICI_DEFAULTS',subprocess.check_output([str(r/'node/bin/node'),'-e',code],env={'OPENSSL_CONF':'/dev/null'},text=True))
