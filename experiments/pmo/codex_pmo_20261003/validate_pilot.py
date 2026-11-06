from run import *
rows={}
for task in ['qed','drd2','amlodipine_mpo']:
    out=ROOT/'control/pilot'/task/'0';result=json.loads((out/'result.json').read_text())
    assert result['status']=='validated_finished' and result['oracle_submissions']==10,result
    ledger=[json.loads(l) for l in (out/'oracle_queries.jsonl').read_text().splitlines()]
    assert [r['index'] for r in ledger]==list(range(1,11))
    requests=[json.loads(p.read_text()) for p in (out/'api').glob('*.json')]
    assert requests
    for r in requests:
        b=r['request'];assert b['model']==MODEL and b['enable_thinking'] is False and b['temperature']==0 and 'max_tokens' not in b
        if 'response' in r:
            assert r['response']['model']==MODEL
            assert not r['response']['choices'][0]['message'].get('reasoning_content')
    receipts=[json.loads(l) for l in (out/'mcp_receipts.jsonl').read_text().splitlines()]
    assert any(r['request']['params']['name']=='python' and not r['result'].get('isError') for r in receipts)
    rows[task]={'passed':True,'actual_api_calls':len(requests),'oracle_submissions':len(ledger),'auc_top10':result['auc_top10']}
dump(ROOT/'pilot_validation.json',{'passed':True,'results':rows,'actual_requests_thinking_disabled':True})
print(json.dumps({'passed':True,'tasks':rows}))
