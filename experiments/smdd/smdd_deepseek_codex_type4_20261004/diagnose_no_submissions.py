from pathlib import Path
import json,collections
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004')
for p in sorted((r/'runs/codex').glob('*/record.json')):
 rec=json.loads(p.read_text())
 if rec['evaluation']!='not_evaluated':continue
 out=p.parent;print('\nTASK',out.name)
 print('RESULT',(out/'result.json').read_text())
 for name in ['workspace/last_message.txt','stderr.log','boundary_error.json','error.log']:
  q=out/name
  if q.exists():print(name,q.read_text(errors='replace')[-2300:])
 for q in sorted((out/'tools').glob('*.json')):
  d=json.loads(q.read_text())
  print('TOOL',q.name,d['name'],'duration',round(d['ended']-d['started'],1),'result',str(d['result'])[-950:])
 for q in sorted((out/'api').glob('*.json'))[-2:]:
  d=json.loads(q.read_text());print('FINAL_API',q.name,'attempts',d['attempts'],'choices',str(d.get('response',{}).get('choices',[]))[-2300:])
 q=out/'events.jsonl'
 if q.exists():print('NATIVE_END',q.read_text(errors='replace')[-1600:])
