"""Reuse completed evaluations, reevaluate submissions, retry infrastructure failures."""
from pathlib import Path
import hashlib
from runtime_safety import read_json_record


def build_plan(tasks,parent):
    parent=Path(parent)
    status=read_json_record(parent/'batch_status.json')
    if not status or 'finished' not in status:
        raise ValueError('Parent run has no valid task ledger')
    inherited={};evaluation_only={};retry=[];pending=[];continuations={}
    for task in tasks:
        prior=status['finished'].get(task,{})
        out=Path(prior.get('reused_from',parent/task))
        agent=read_json_record(out/'agent_result.json')
        evaluation=read_json_record(out/'evaluation/result.json')
        submitted=agent and agent.get('status')=='submitted' and (out/'solution.smi').is_file()
        if submitted and evaluation and evaluation.get('status') in ('passed','failed'):
            if task not in status['finished']:raise ValueError('Completed task missing from ledger: '+task)
            inherited[task]={**status['finished'][task],'reused_from':str(out)}
        elif submitted:
            evaluation_only[task]={'source':str(out),'solution_sha256':hashlib.sha256((out/'solution.smi').read_bytes()).hexdigest()}
        elif agent and agent.get('status')=='resource_blocked':
            continuations[task]={'source':str(out),'budget_used':agent['budget_used']}
        elif out.exists():
            retry.append(task)
        else:
            pending.append(task)
    assert len(inherited)+len(evaluation_only)+len(continuations)+len(retry)+len(pending)==len(tasks)
    return {'parent':str(parent),'inherited':inherited,'evaluation_only':evaluation_only,
            'retry_infrastructure':retry,'not_started':pending,'continuations':continuations}
