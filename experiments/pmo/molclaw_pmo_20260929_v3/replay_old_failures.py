"""Read-only replay of actual v1 failures through the v2 boundary logic."""
import json
import os
from pathlib import Path
from guard import reason
from scp_gateway import charge_molecules
from validation import final_answer
from runner import dump,ROOT

old=Path('/data2/chenfuxin/molclaw_pmo_20260928')
scoring=0;blocked=0;generation=0;write_checks=0;bad_final=0;details=[]
for out in (old/'runs').glob('*/0'):
    os.environ['PMO_WORKSPACE_ROOT']=str(out)
    events=[json.loads(line) for line in (out/'events.jsonl').read_text().splitlines()]
    calls={}
    for event in events:
        for b in event.get('message',{}).get('content',[]):
            if not isinstance(b,dict):continue
            if b.get('type')=='tool_use':calls[b['id']]=b
            if b.get('type')!='tool_result':continue
            call=calls.get(b.get('tool_use_id'),{});name=call.get('name');args=call.get('input',{})
            if out.parent.name=='valsartan_smarts' and name=='Bash' and not b.get('is_error') and 'def sc(' in args.get('command',''):
                scoring+=1
                issue=reason({'tool_name':'Bash','cwd':str(out),'tool_input':args})
                blocked+=bool(issue)
                if not issue:details.append({'missed_command':args})
            if name=='mcp__molclaw-scp__reinvent_mol2mol_sampling' and b.get('is_error') and 'PreToolUse' in str(b.get('content')):
                assert charge_molecules(out.parent.name,'reinvent_mol2mol_sampling',args)==[]
                generation+=1
            if out.parent.name=='mestranol_similarity' and name=='Write':
                assert reason({'tool_name':'Write','cwd':str(out/'.claude/skills'),'tool_input':args}) is None
                write_checks+=1
    final=next(e for e in reversed(events) if e.get('type')=='result')
    if out.parent.name in ['celecoxib_rediscovery','fexofenadine_mpo','thiothixene_rediscovery','zaleplon_mpo']:
        assert final_answer(final.get('result','')) is None
        bad_final+=1
assert scoring>0 and scoring==blocked and generation>0 and write_checks>0 and bad_final==4
report={'passed':True,'actual_unbudgeted_score_commands':scoring,'now_blocked':blocked,
        'previously_blocked_generation_calls_now_allowed':generation,'workspace_write_regressions':write_checks,
        'invalid_endings_correctly_rejected':bad_final,'details':details}
dump(ROOT/'historical_regression.json',report)
print(json.dumps(report))
