"""Independent read-only acceptance of persisted results and external receipts."""
import json
from pathlib import Path
import sys
from runner import ROOT,dump
from oracle_server import OracleService,canonical
from scp_gateway import charge_molecules
from validation import final_answer,audit
from trajectory import complete_auc


def check(task):
    c=ROOT/'control'/task/'0';out=ROOT/'runs'/task/'0'
    r=json.loads((c/'result.json').read_text());state=json.loads((c/'state.json').read_text())
    ledger=OracleService(c,task).ledger()
    assert r['status']=='validated_finished' and state['status']=='validated_finished'
    assert r['oracle_submissions']==len(ledger.rows)==1000
    assert r['final_valid'] and r['final_evaluated'] and (out/'result.md').is_file()
    assert ledger.buffer[canonical(r['final_answer'])][0]==r['final_score']
    assert abs(r['auc_top10']-complete_auc(ledger.rows)[0])<1e-12
    events=[json.loads(s) for s in (c/f'events_{state["segment"]:02d}.jsonl').read_text().splitlines()]
    final=next(e for e in reversed(events) if e.get('type')=='result')
    assert final_answer(final.get('result',''))==r['final_answer']
    receipt_report=audit(c,ledger);assert receipt_report['passed']
    external_queries=0
    for line in (c/'mcp_receipts.jsonl').read_text().splitlines():
        rec=json.loads(line)
        if rec['server']!='SCPGateway' or rec['result'].get('isError'):continue
        params=rec['request']['params'];expected=charge_molecules(task,params['name'],params.get('arguments',{}))
        receipt=[]
        for block in rec['result'].get('content',[]):
            if block.get('type')!='text':continue
            try:value=json.loads(block['text'])
            except ValueError:continue
            if isinstance(value,dict):receipt.extend(value.get('pmo_budget_receipt',[]))
        assert [row['raw'] for row in receipt]==expected
        for row in receipt:assert row==ledger.events[row['event_id']]
        external_queries+=len(receipt)
    return {'task':task,'passed':True,'queries':len(ledger.rows),'external_scoring_queries':external_queries,
            'final_score':r['final_score'],'same_session_recoveries':r['recovery_segments']}


if __name__=='__main__':
    tasks=['qed','valsartan_smarts','mestranol_similarity','fexofenadine_mpo'] if sys.argv[1]=='pilot' else sys.argv[1:]
    results=[check(task) for task in tasks]
    dump(ROOT/'pilot_acceptance.json',{'passed':True,'results':results})
    print(json.dumps(results))
