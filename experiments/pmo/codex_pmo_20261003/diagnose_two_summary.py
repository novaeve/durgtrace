from pathlib import Path
import json,collections
ROOT=Path('/data2/chenfuxin/codex_pmo_20261003/control/full')
for task in ['zaleplon_mpo','isomers_c7h8n2o2']:
 out=ROOT/task/'0';ledger=[json.loads(x) for x in (out/'oracle_queries.jsonl').read_text().splitlines()]
 rec=[json.loads(x) for x in (out/'mcp_receipts.jsonl').read_text().splitlines()]
 api=[]
 for p in sorted((out/'api').glob('*.json')):
  d=json.loads(p.read_text());c=(d.get('response',{}).get('choices') or [{}])[0]
  if c.get('finish_reason')=='length':api.append(p.name)
 errors=[]
 for x in rec:
  try:value=json.loads(x['result']['content'][0]['text'])
  except ValueError:continue
  if 'error' in value:errors.append(value['error'])
 print(json.dumps({'task':task,'ledger_status':dict(collections.Counter(x['status'] for x in ledger)),'initial_score':ledger[0]['score'],'later_scores':[x['score'] for x in ledger[1:]],'scored_unique':len({x['canonical'] for x in ledger if x['canonical']}),'truncations':api,'tools':dict(collections.Counter(x['request']['params']['name'] for x in rec)),'tool_guard_rejections':errors}))
