from pathlib import Path
import json,collections
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');rows=[]
for p in sorted((r/'runs/codex').glob('*/record.json')):
 rec=json.loads(p.read_text())
 if rec['evaluation']!='not_evaluated':continue
 out=p.parent;result=json.loads((out/'result.json').read_text());apis=sorted((out/'api').glob('*.json'));last=json.loads(apis[-1].read_text())
 choice=last.get('response',{}).get('choices',[{}])[0];msg=choice.get('message',{})
 tools=[json.loads(q.read_text()) for q in sorted((out/'tools').glob('*.json'))]
 ev=[]
 for ln in (out/'events.jsonl').read_text(errors='replace').splitlines():
  try:ev.append(json.loads(ln))
  except ValueError:continue
 row={'task':out.name,'calls':result['calls'],'tokens':result['tokens'],'boltz':result['boltz_calls'],'admet':result['admet_calls'],'agent_exit':result['exit_code'],'boundary_error':result.get('boundary_error'),'final_finish_reason':choice.get('finish_reason'),'final_tool_calls':len(msg.get('tool_calls') or []),'final_text':msg.get('content'),'response_http':last['attempts'][-1].get('status'),'final_event_type':ev[-1]['type'],'native_turn_failures':sum(d['type'] in ['error','turn.failed'] for d in ev),'last_tool':tools[-1]['name'] if tools else None,'last_tool_result':str(tools[-1]['result'])[-700:] if tools else None,'error_tools':[{'name':d['name'],'result':str(d['result'])[:350]} for d in tools if str(d['result']).startswith(('ERROR:','Traceback'))],'solution_exists':(out/'workspace/solution.smi').exists()}
 rows.append(row);print(json.dumps(row))
(r/'diagnosis_no_submissions.json').write_text(json.dumps(rows,indent=2));print('UNSCORED_TOTAL',len(rows))
