from pathlib import Path
import json,subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004');out=r/'runs/solpi/smdd_004_ACE_4'
api={}
for q in sorted((out/'api').glob('*.json')):
 d=json.loads(q.read_text())
 for c in d.get('response',{}).get('choices',[]):
  for call in c['message'].get('tool_calls') or []:
   if call['function']['name']=='submit':api[call['id']]=d.get('ended')
seen=0
for ln in (out/'events.jsonl').read_text().splitlines():
 try:d=json.loads(ln)
 except ValueError:continue
 if d.get('type')=='message_end':
  msg=d.get('message',{})
  if msg.get('toolName')=='submit' and seen<4:
   print('SUBMIT_CLIENT',msg.get('toolCallId'),'api_end',api.get(msg.get('toolCallId')),'result',msg.get('content'),'time',msg.get('timestamp'));seen+=1
code="const s=process.binding('natives')['internal/deps/undici/undici']; const pat=/headersTimeout|kHeadersTimeout/g; let m,n=0; while((m=pat.exec(s))&&n++<18)console.log(s.slice(Math.max(0,m.index-120),m.index+260));"
print('NODE_HEADERS_TIMEOUT_SOURCE',subprocess.check_output([str(r/'node/bin/node'),'-e',code],env={'OPENSSL_CONF':'/dev/null'},text=True))
