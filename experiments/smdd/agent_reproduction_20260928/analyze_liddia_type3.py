import collections,json,statistics
from pathlib import Path
from rdkit import Chem
ROOT=Path('/data2/chenfuxin/liddia_smdd_type3_20261004')
OUT=ROOT/'runs/full_high_v1'
def canon(s):
    m=Chem.MolFromSmiles(s)
    return Chem.MolToSmiles(m) if m else s
metrics=collections.defaultdict(list);rows=[];actions=collections.Counter();ga=[]
for task in sorted(OUT.glob('smdd_003*')):
    if not task.is_dir():continue
    evaluation=json.loads((task/'evaluation/result.json').read_text())
    for step in evaluation['steps']:metrics[step['name']].append(step)
    result=json.loads((task/'agent_result.json').read_text())
    trajectory=json.loads((task/'trajectory.json').read_text())
    sets=json.loads((task/'molecule_sets.json').read_text()) if (task/'molecule_sets.json').exists() else {}
    journal=[json.loads(x) for x in (task/'budget.jsonl').read_text().splitlines() if x.strip()]
    reservations=[x for x in journal if x.get('event')=='reserved' and x.get('kind')=='boltz']
    measured=[x for x in journal if x.get('event')=='result' and x.get('kind')=='boltz']
    unique={canon(x['smiles']) for x in reservations}
    code_errors=0;tool_errors=[];generations=[]
    for event in trajectory:
        action=event.get('action','parse_error');actions[action]+=1
        metadata=event.get('metadata',{})
        code_errors+=len(metadata.get('errors',[]))
        if metadata.get('error'):tool_errors.append(metadata['error'])
        if action.startswith('GENERATE') and event.get('output') in sets:
            generations.append(len(sets[event['output']]))
        if action.startswith('OPTIMIZE'):
            scores=metadata.get('scores',{})
            source=event.get('input',[''])[0]
            input_smiles={canon(x['SMILES']) for x in sets.get(source,[])}
            scored={canon(x) for x in scores}
            ga.append({'task':task.name,'objective':metadata.get('objective'),
                       'calls':metadata.get('score_calls'),'stop':metadata.get('stop'),
                       'scored_new_molecules':len(scored-input_smiles),
                       'scored_input_molecules':len(scored&input_smiles)})
    submitted=canon((task/'solution.smi').read_text().strip())
    counts=collections.Counter(canon(x['smiles']) for x in reservations)
    probability=[]
    for entry in measured:
        value=entry.get('result',{})
        if 'affinity_probability_binary' in value:probability.append(value['affinity_probability_binary'])
    rows.append({'task':task.name,'boltz_calls':len(reservations),'unique_boltz_molecules':len(unique),
                 'duplicate_calls':sum(x-1 for x in counts.values()),'llm_calls':result['llm_calls'],
                 'tokens':result['tokens'],'generations':generations,'code_errors':code_errors,
                 'tool_errors':tool_errors,'submitted_was_scored':submitted in unique,
                 'best_agent_binding_probability':max(probability) if probability else None})
summary={'tasks':len(rows),'metrics':{},'actions':dict(actions),'graphga':{},'budget':{}}
for name,steps in metrics.items():
    values=[s['result'] for s in steps if isinstance(s.get('result'),(int,float))]
    summary['metrics'][name]={'statuses':dict(collections.Counter(s['status'] for s in steps)),
                            'median':statistics.median(values) if values else None,
                            'min':min(values) if values else None,'max':max(values) if values else None}
learned=[g for g in ga if g['objective']=='BindingAffinity']
summary['graphga']={'calls':len(ga),'tasks_used':len({g['task'] for g in ga}),
                    'objectives':dict(collections.Counter(g['objective'] for g in ga)),
                    'learned_calls':len(learned),'learned_with_no_new_scored_molecules':sum(g['scored_new_molecules']==0 for g in learned),
                    'learned_stops':dict(collections.Counter(g['stop'] for g in learned))}
summary['budget']={'boltz_calls':sum(r['boltz_calls'] for r in rows),'duplicate_calls':sum(r['duplicate_calls'] for r in rows),
                   'tasks_with_duplicates':sum(r['duplicate_calls']>0 for r in rows),
                   'tasks_exhausted_boltz':sum(r['boltz_calls']==8 for r in rows),
                   'median_unique_boltz_molecules':statistics.median(r['unique_boltz_molecules'] for r in rows),
                   'median_llm_calls':statistics.median(r['llm_calls'] for r in rows),
                   'tasks_submitted_unscored':sum(not r['submitted_was_scored'] for r in rows),
                   'successful_generation_calls':sum(len(r['generations']) for r in rows),
                   'median_generated_pool':statistics.median(n for r in rows for n in r['generations']),
                   'tool_errors':dict(collections.Counter(e.split(':')[0] for r in rows for e in r['tool_errors'])),
                   'tasks_agent_saw_prob_above_07':sum(r['best_agent_binding_probability'] is not None and r['best_agent_binding_probability']>0.7 for r in rows)}
report={'summary':summary,'tasks':rows,'graphga_events':ga}
(ROOT/'analysis_20261005.json').write_text(json.dumps(report,indent=2))
print(json.dumps(summary))
