from pathlib import Path
import json,collections,hashlib
ROOT=Path('/data2/chenfuxin/codex_pmo_20261003')
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12]
report={}
for out in sorted((ROOT/'control/full').glob('*/0')):
 r=json.loads((out/'result.json').read_text())
 if r['status']=='validated_finished':continue
 task=out.parent.name;paths=sorted((out/'api').glob('*.json'));trunc=[];responses=collections.Counter();requests=collections.Counter();samples=[]
 for i,p in enumerate(paths):
  d=json.loads(p.read_text());req=d['request'];resp=d.get('response',{});choice=(resp.get('choices') or [{}])[0];msg=choice.get('message',{});calls=msg.get('tool_calls') or []
  normalized={'content':msg.get('content'),'tools':[(x['function']['name'],x['function']['arguments']) for x in calls]}
  responses[digest(normalized)]+=1;requests[digest(req)]+=1
  if i in [0,1,2,len(paths)//2,len(paths)-2,len(paths)-1]:
   history=req['messages'];toolhistory=[m for m in history if m.get('role')=='tool']
   samples.append({'file':p.name,'messages':len(history),'roles':dict(collections.Counter(m.get('role') for m in history)),'last_messages':history[-3:],'response':msg,'usage':resp.get('usage')})
  if choice.get('finish_reason')=='length':
   text=(msg.get('content') or '')+'\n'+'\n'.join(x['function']['arguments'] for x in calls)
   lines=text.splitlines();rep=collections.Counter(lines)
   trunc.append({'file':p.name,'usage':resp.get('usage'),'chars':len(text),'tool_names':[x['function']['name'] for x in calls],'head':text[:600],'tail':text[-900:],'most_repeated_lines':rep.most_common(3),'line_count':len(lines),'unique_lines':len(rep)})
 receipts=[json.loads(l) for l in (out/'mcp_receipts.jsonl').read_text().splitlines()] if (out/'mcp_receipts.jsonl').exists() else []
 toolcounts=collections.Counter(x['request']['params']['name'] for x in receipts)
 argcounts=collections.Counter(digest(x['request']['params']) for x in receipts)
 ledger=[json.loads(l) for l in (out/'oracle_queries.jsonl').read_text().splitlines()]
 item={'status':r['status'],'submissions':len(ledger),'api_calls':len(paths),'unique_request_bodies':len(requests),'unique_response_actions':len(responses),'most_repeated_response':responses.most_common(1),'tool_counts':dict(toolcounts),'most_repeated_tool_args':argcounts.most_common(1),'truncations':trunc,'samples':samples,'last_receipts':receipts[-3:]}
 report[task]=item
 print(json.dumps({'task':task,**{k:item[k] for k in ['status','submissions','api_calls','unique_request_bodies','unique_response_actions','most_repeated_response','tool_counts','most_repeated_tool_args']},'truncations':[{'file':t['file'],'usage':t['usage'],'chars':t['chars'],'tool_names':t['tool_names'],'line_count':t['line_count'],'unique_lines':t['unique_lines']} for t in trunc]}))
(ROOT/'diagnosis_20261004.json').write_text(json.dumps(report,indent=2))
