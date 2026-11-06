from pathlib import Path
import json,re
base=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/pilot_parserfix1/smdd_004_ABL1_1')
status={}
for name in ['agent_result.json','evaluation/result.json']:
    p=base/name
    if p.exists():
        data=json.loads(p.read_text());status[name]=data if name=='agent_result.json' else {'status':data.get('status'),'steps':data.get('steps')}
p=base/'llm_calls.json'
if p.exists():
    calls=json.loads(p.read_text());status['llm_calls']=len(calls)
    if calls:
        status['last_label']=calls[-1]['label']
        status['last_action']=re.findall(r'Action:.*',calls[-1].get('output') or '')
p=base/'trajectory.json'
if p.exists():
    events=json.loads(p.read_text());status['completed_actions']=len(events)
    status['actions']=[{'action':x.get('action'),'input':x.get('input'),'output':x.get('output')} for x in events]
p=base/'budget.jsonl'
if p.exists():
    events=[json.loads(x) for x in p.read_text().splitlines() if x]
    status['budget_used']={k:sum(x['event']=='reserved' and x['kind']==k for x in events) for k in ['admet','boltz']}
    status['oracle_errors']=[x for x in events if x['event']=='error']
for p in sorted((base/'generation').glob('*/sampling.log'),key=lambda p:p.stat().st_mtime)[-1:]:
    matches=re.findall(r'\[Pool\] Queue \d+ \| Finished \d+ \| Failed \d+',p.read_text(errors='replace'))
    status['pocket_progress']=matches[-1] if matches else 'initializing'
    status['pocket_sampling_steps_logged']=len(matches)
print(json.dumps(status,ensure_ascii=False,indent=2))
