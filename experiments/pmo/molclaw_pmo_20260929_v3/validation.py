import json
import re
from oracle_server import canonical


def final_answer(text):
    # Compaction summaries and quoted output instructions are not submissions.
    if re.search(r'<(?:summary|analysis)>',text,re.I):return None
    matches=re.findall(r'<answer>\s*([^<>]+?)\s*</answer>',text,re.S|re.I)
    if len(matches)!=1:return None
    sm=matches[0].strip().strip('`').strip()
    if '\n' in sm or canonical(sm) is None:return None
    return sm


def audit(control,ledger):
    receipts=[]
    path=control/'mcp_receipts.jsonl'
    if path.exists():receipts=[json.loads(s) for s in path.read_text().splitlines()]
    acknowledged=set();errors=[]
    for event in receipts:
        result=event['result']
        for content in result.get('content',[]):
            if content.get('type')!='text':continue
            try:payload=json.loads(content['text'])
            except (ValueError,TypeError):continue
            if not isinstance(payload,dict):continue
            rows=payload.get('results',[]) if event['server']=='OracleService' else payload.get('pmo_budget_receipt',[])
            for row in rows:
                if not isinstance(row,dict) or 'event_id' not in row:continue
                if row!=ledger.events.get(row['event_id']):errors.append('receipt_mismatch:'+str(row.get('event_id')))
                acknowledged.add(row['event_id'])
    expected={r['event_id'] for r in ledger.rows if r['event_id'].endswith('/agent_tool')}
    if not expected.issubset(acknowledged):errors.append('missing_pmo_receipt')
    # All SCP oracle reservations persist even if its external call fails.
    return {'passed':not errors,'errors':errors,'oracle_submissions':len(ledger.rows),'receipt_count':len(receipts),
            'acknowledged_queries':len(acknowledged),'budget_within_cap':len(ledger.rows)<=ledger.budget}
