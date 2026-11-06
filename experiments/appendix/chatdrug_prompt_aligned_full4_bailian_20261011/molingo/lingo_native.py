"""Original MolLingo generation, model-only selection, one scored submission."""
import argparse,ast,collections,concurrent.futures,fcntl,json,re,time
import runner as r
from lingo_relay import Relay,MODEL
from common import ROOT, score
r.Relay=Relay

def parse_selection(text,n):
 candidates=[text.strip()]+re.findall(r'```(?:json)?\s*(.*?)```',text,re.S)
 objects=[]
 for item in candidates:
  try:obj=json.loads(item)
  except ValueError:continue
  if isinstance(obj,dict) and set(obj)=={'candidate_id'}:objects.append(obj)
 if not objects:raise ValueError('INVALID_SINGLE_SELECTION')
 ids=[obj['candidate_id'] for obj in objects]
 if any(type(i) is not int or not 1<=i<=n for i in ids) or len(set(ids))!=1:raise ValueError('INVALID_SINGLE_SELECTION')
 return ids[0]-1

def submit_one(case,candidates,complete):
 if not candidates:return None,None,'NO_CANDIDATES'
 if len(candidates)==1:return candidates[0],0,None
 prompt=("You are a molecular chemist. You must submit exactly ONE final molecule for this task.\n"
  "Task: "+case['instruction']+"\nStarting molecule: "+case['smiles']+"\n"
  "Below are the molecules assembled from your proposed block substitutions. The order is enumeration order, NOT a quality ranking. "
  "Choose the single candidate you judge most likely to satisfy the task. No evaluator scores or test feedback are available. "
  "Do not generate new candidates. Return only a JSON object with exactly one integer field candidate_id, using the IDs below. "
  "Example format: {\"candidate_id\": 2}\nCandidates:\n"+
  '\n'.join(f'{i+1}: {sm}' for i,sm in enumerate(candidates)))
 idx=parse_selection(complete(prompt,'single_final_selection'),len(candidates))
 return candidates[idx],idx,None

def run_case(case,stage):
 out=ROOT/'native/MolLingo'/stage/case['id'];out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 relay=r.Relay(out/'api_calls.json');start=time.monotonic();row={'id':case['id'],'case':case,'status':'running'}
 def complete(prompt,label):
  try:return relay.complete([{'role':'user','content':prompt}],label)
  except r.p.RelayError as e:
   if str(e)!='OUTPUT_TRUNCATED':raise
   return relay.calls[-1]['output']
 try:
  ns=r.core_namespace(lambda prompt:complete(prompt,'block_substitution'))
  candidates=ns['optimize_mol_tomg'](case['smiles'],main_task=case['property'],trend='increase' if case['objectives'][0][1]==1 else 'decrease',variants=3,task_instruction=case['instruction'])
  row['raw_candidates']=candidates;row['candidate_count_raw']=len(candidates)
  candidate,index,failure=submit_one(case,candidates,complete)
  # Sole benchmark evaluation: only the model-selected final output is scored.
  row.update(status='complete',candidate=candidate,selected_index=index,score=score(case,candidate),evaluation_calls=1,model_failure=failure)
 except ValueError as e:
  if str(e) not in ['MODEL_MODIFICATION_LIST_UNPARSEABLE','INVALID_SINGLE_SELECTION']:
   row.update(status='error',error=type(e).__name__)
  else:row.update(status='complete',candidate=None,selected_index=None,score=score(case,None),evaluation_calls=1,model_failure=str(e))
 except Exception as e:row.update(status='error',error=str(e) if isinstance(e,r.p.RelayError) else type(e).__name__)
 row['llm_calls']=len(relay.calls);row['api_requests']=sum(len(x['attempts']) for x in relay.calls)
 row['seconds']=round(time.monotonic()-start,3);row['truncated_responses']=sum(x.get('stop_reason')=='max_tokens' for x in relay.calls)
 row['usage']={k:sum(x.get('usage',{}).get(k,0) or 0 for x in relay.calls) for k in ['input_tokens','output_tokens','cache_read_input_tokens']}
 r.dump(out/'result.json',row)
 print(json.dumps({'id':case['id'],'status':row['status'],'success':row.get('score',{}).get('success'),'model_failure':row.get('model_failure'),'error':row.get('error'),'calls':row['llm_calls']}),flush=True)
 return row

def summarize(stage):
 rows=[json.loads(f.read_text()) for f in (r.ROOT/'runs'/('single_bailian_'+stage)).glob('*/result.json')];groups={}
 for row in rows:
  key='ChatDrug' if row['case']['benchmark']=='ChatDrug' else row['case']['property'];g=groups.setdefault(key,collections.Counter())
  g[row['status']]+=1;g['success']+=bool(row.get('score',{}).get('success'));g['model_failures']+=bool(row.get('model_failure'));g['llm_calls']+=row['llm_calls']
 result={'processed':len(rows),'groups':groups,'errors':[{'id':x['id'],'error':x.get('error')} for x in rows if x['status']=='error']}
 r.dump(r.ROOT/'runs'/('single_bailian_'+stage)/'summary.json',result);return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);stage=ap.parse_args().stage
 out=r.ROOT/'runs'/('single_bailian_'+stage);out.mkdir(parents=True,exist_ok=True)
 lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=json.loads((r.benchmark.PREP/'cases.json').read_text())
 if stage=='pilot':
  buckets={}
  for c in cases:buckets.setdefault((c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction']),c)
  cases=list(buckets.values());assert len(cases)==34
 else:
  gate=json.loads((r.ROOT/'runs/single_bailian_pilot/summary.json').read_text());assert gate['processed']==34 and not gate['errors']
 hashes={n:r.p.sha(r.ROOT/n) for n in ['single_bailian_runner.py','bailian_relay.py','runner.py','core_fixed.py']}
 cfg={'model':MODEL,'provider':'Alibaba Bailian OpenAI-compatible','enable_thinking':False,'temperature':0,'thinking':'disabled','max_tokens':'omitted; provider default','workers':2,'expected':len(cases),'code_hashes':hashes,'policy':'original raw candidate generation then model selects one; only submitted candidate scored; no oracle selection or no-op exclusion','max_logical_calls':2,'input_manifest':r.p.sha(r.benchmark.PREP/'manifest.json')}
 config_path=out/'run_config.json'
 if config_path.exists():assert json.loads(config_path.read_text())==cfg
 else:r.dump(config_path,cfg)
 pending=[c for c in cases if not (out/c['id']/'result.json').exists()]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  jobs=[pool.submit(run_case,c,stage) for c in pending]
  for job in concurrent.futures.as_completed(jobs):job.result();summarize(stage)
 result=summarize(stage);print(json.dumps(result),flush=True)
 if result['errors']:raise SystemExit(2)

if __name__=='__main__':main()
