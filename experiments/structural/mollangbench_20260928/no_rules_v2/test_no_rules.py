"""Control-flow and answer-isolation regression tests; no API calls."""
import json,sys,tempfile
from pathlib import Path
import run_agents as r

sys.addaudithook(r.deny_gold)
try:
    (r.ROOT/'data/answers.json').read_text()
    raise AssertionError('Gold was accessible')
except PermissionError:
    pass
cases=json.loads((r.ROOT/'data/cases.json').read_text())
assert len(cases)==800
phrase='Return the resulting SMILES string enclosed within <smiles> and </smiles> tags.'
for case in cases:
    for method in ['chatdrug','agentdrug']:
        assert case['prompt'].count(phrase)==1
        assert r.public_prompt(case,method).split('Give me five molecules')[0] if method=='chatdrug' else True

class Fake:
    def __init__(self,outputs):self.outputs=iter(outputs);self.messages=[]
    def complete(self,messages,label,cap=None):
        self.messages.append(json.loads(json.dumps(messages)))
        return next(self.outputs)

tested=0
with tempfile.TemporaryDirectory() as tmp:
    out=Path(tmp)
    for task in ['edit','generation']:
        c=dict(next(c for c in cases if c['task']==task))
        c['original_smiles']='CCCCCC' if task=='edit' else None
        fake=Fake(['- CCCCCCO\n- CCCCCCN'])
        pred,state=r.chatdrug(c,fake,out)
        assert pred=='CCCCCCO' and state['generation_calls']==1
        assert state['stop_reason']=='reference_verifier_unavailable'
        assert state['task_status']=='not_evaluated'
        tested+=1
        limit=4 if task=='edit' else 5
        fake=Fake(['invalid','CCCCCCO']+['CCCCCCN']*(limit-2))
        pred,state=r.agentdrug(c,fake,out)
        assert pred=='CCCCCCN' and len(fake.messages)==limit
        assert state['validity_feedback_count']==1
        assert 'not chemically valid' in fake.messages[1][0]['content']
        assert 'Task correctness has not been evaluated' in fake.messages[2][0]['content']
        assert 'which is correct and similar' not in json.dumps(fake.messages)
        tested+=1
    c=dict(c,original_smiles='CCCCCC')
    fake=Fake(['- CCCCCC'])
    pred,state=r.chatdrug(c,fake,out)
    assert pred is None and state['retrieval_attempts']==0
    tested+=1
print(json.dumps({'passed':True,'flow_tests':tested,'public_cases':len(cases),'gold_blocked':True}))
