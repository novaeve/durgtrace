import collections,json
import runner as r
groups={};rows=[]
for f in sorted((r.ROOT/'runs/full').glob('*/result.json')):
 row=json.loads(f.read_text());case=row['case'];candidate=None;raw=[];failure=None
 if row.get('model_output_failure'):failure='model_output_parse_failure'
 elif row['status']!='complete':failure='run_error'
 else:
  calls=json.loads((f.parent/'api_calls.json').read_text())
  assert len(calls)==1
  # Replay original candidate assembly from saved model output; no new LLM calls.
  ns=r.core_namespace(lambda prompt:calls[0]['output'])
  raw=ns['optimize_mol_tomg'](case['smiles'],main_task=case['property'],trend='increase' if case['objectives'][0][1]==1 else 'decrease',variants=3,task_instruction=case['instruction'])
  assert len(raw)==row['candidate_count_raw']
  if raw:candidate=raw[0]
  else:failure='empty_return_list'
 score=r.benchmark.score(case,candidate)
 key='ChatDrug' if case['benchmark']=='ChatDrug' else case['property'];g=groups.setdefault(key,collections.Counter())
 g['total']+=1;g['success']+=bool(score['success']);g['valid']+=bool(score['valid']);g['no_output']+=candidate is None
 if candidate is not None:
  control=row['no_modification_control']['candidate']
  assert candidate==control,(case['id'],candidate,control)
  g['first_equals_unmodified_reassembly']+=1
 rows.append({'id':case['id'],'group':key,'first_returned':candidate,'score':score,'failure':failure})
assert len(rows)==7100
out={'policy':'raw returned list index 0 only; no filtering, ranking or extra model calls; missing/invalid output fails','groups':groups,'rows':rows}
r.dump(r.ROOT/'runs/full/first_returned.json',out)
print(json.dumps({'groups':groups,'rows':len(rows)}),flush=True)
