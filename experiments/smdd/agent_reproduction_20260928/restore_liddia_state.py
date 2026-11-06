from pathlib import Path
import json
import re
import pandas as pd
from rdkit import Chem
from liddia_action_parser import parse_action


def restore(out,agent,memory,known,events,gate,ga,pocket,actions):
    out=Path(out)
    previous=json.loads((out/'agent_result.json').read_text())
    if previous['status']!='resource_blocked':raise ValueError('Only resource-blocked tasks can resume')
    if previous['budget_used']!=gate.used:raise ValueError('Budget mismatch')
    agent.calls=json.loads((out/'llm_calls.json').read_text())
    agent.tokens=sum(c.get('usage',{}).get('total_tokens',0) for c in agent.calls)
    if len(agent.calls)!=previous['llm_calls'] or agent.tokens!=previous['tokens']:
        raise ValueError('LLM accounting mismatch')
    reservations={}
    for line in (out/'budget.jsonl').read_text().splitlines():
        event=json.loads(line);key=(event['kind'],event['call'])
        if event['event']=='reserved':reservations[key]=event['smiles']
        elif event['event']=='result':
            smi=Chem.MolToSmiles(Chem.MolFromSmiles(reservations[key]))
            known.setdefault(smi,{}).update(event['result'])
    sets=json.loads((out/'molecule_sets.json').read_text())
    for key,data in sorted(sets.items(),key=lambda kv:int(kv[0][3:])):
        if key in memory.stream:memory.stream[key]['data']=pd.DataFrame(data)
        else:
            added=memory.add_mol(data=pd.DataFrame(data),action='restored measured state',metrics={},return_id=True)
            if added!=key:raise ValueError('Molecule ID mismatch')
    events.extend(json.loads((out/'trajectory.json').read_text()))
    decisions=[c for c in agent.calls if c['label']=='decision']
    next_step=max((e['step'] for e in events),default=-1)+1
    if len(decisions)!=next_step+1:raise ValueError('Expected exactly one interrupted decision')
    key,inputs,desc=parse_action(decisions[-1]['output'],actions)
    events.append({'step':next_step,'action':key,'input':inputs+([desc] if key.startswith('CODE') else []),
                   'output':'NONE','metadata':{'error':previous['error'],'restored_resource_interruption':True},
                   'budget_used':dict(gate.used)})
    for event in events:
        if 'action' not in event:continue
        inputs=list(event['input'])
        if event['action'].startswith('CODE') and (not inputs or re.fullmatch(r'MOL\d+',str(inputs[-1]))):
            _,_,desc=parse_action(decisions[event['step']]['output'],actions);inputs.append(desc)
        memory.add_history(action_id=event['action'],action_input=[str(x) for x in inputs],
                           action_output=event.get('output','NONE'),metadata=event.get('metadata',{}))
    origin=json.loads((out/'resume_origin.json').read_text()) if (out/'resume_origin.json').exists() else {'source':str(out)}
    rng_root=Path(origin['source'])
    for _ in (rng_root/'optimization').glob('graphga_*'):ga.rng.randrange(1,1_000_000_000)
    for _ in (rng_root/'generation').glob('pocket_*'):pocket.rng.randrange(1,1_000_000_000)
    return next_step+1,'Resumed after resource interruption. Previous failed attempt remains charged. '+previous['error']
