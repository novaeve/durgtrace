from pathlib import Path
import json,collections,re
ROOT=Path('/data2/chenfuxin/codex_pmo_20261003/control/full')
for task in ['zaleplon_mpo','isomers_c7h8n2o2']:
    out=ROOT/task/'0'
    ledger=[json.loads(x) for x in (out/'oracle_queries.jsonl').read_text().splitlines()]
    print(json.dumps({'task':task,'result':json.loads((out/'result.json').read_text()),'ledger':[{'index':x['index'],'status':x['status'],'score':x['score'],'smiles':x['raw'],'event':x['event_id']} for x in ledger]},ensure_ascii=False))
    for p in sorted((out/'api').glob('*.json')):
        d=json.loads(p.read_text());r=d.get('response',{});c=(r.get('choices') or [{}])[0];m=c.get('message',{});calls=m.get('tool_calls') or []
        text=(m.get('content') or '')+'\n'+'\n'.join(x['function']['arguments'] for x in calls)
        item={'api':p.name,'finish':c.get('finish_reason'),'tokens':r.get('usage',{}).get('completion_tokens'),'tools':[x['function']['name'] for x in calls]}
        if c.get('finish_reason')=='length':
            item.update(head=text[:450],tail=text[-650:])
        else:item['snippet']=text[:700]
        print(json.dumps(item,ensure_ascii=False))
    receipts=[json.loads(x) for x in (out/'mcp_receipts.jsonl').read_text().splitlines()]
    for x in receipts:
        params=x['request']['params'];tool=params['name'];result=x['result']
        print(json.dumps({'executed_tool':tool,'args':str(params.get('arguments',{}))[:350],'result':str(result)[:850]},ensure_ascii=False))
