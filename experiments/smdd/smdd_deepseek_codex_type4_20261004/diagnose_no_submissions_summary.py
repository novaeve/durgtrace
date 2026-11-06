from pathlib import Path
import json
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');ds=json.loads((r/'diagnosis_no_submissions.json').read_text())
for d in ds:
 text=d['final_text'] or '';print('TASK',d['task'],'CALLS',d['calls'],'STOP',d['final_finish_reason'],'TEXT_CHARS',len(text),'TEXT_END',repr(text[-330:]))
 out=r/'runs/codex'/d['task'];q=sorted((out/'api').glob('*.json'))[-1];a=json.loads(q.read_text());req=a['request']
 print('FINAL_USAGE',a['response'].get('usage'),'REQUEST_SETTINGS',{k:v for k,v in req.items() if k not in ['messages','tools']})
 for m in req['messages'][-3:]:
  if m['role'] in ['user','system']:print('LAST_INPUT',m['role'],str(m.get('content'))[-1600:])
 if '<summary>' in text:
  for m in req['messages']:
   if m['role']=='user' and ('summary' in str(m.get('content')).lower() or 'summar' in str(m.get('content')).lower()):print('SUMMARY_REQUEST',str(m['content'])[:1600])
