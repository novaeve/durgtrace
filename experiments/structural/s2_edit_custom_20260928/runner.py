"""Source-derived ChatDrug and AgentDrug episodes on S2-mini MolEdit/MolCustom."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse,concurrent.futures,fcntl,io,json,re,sys,time,types,traceback,warnings
from pathlib import Path
import pandas as pd
from rdkit import Chem,DataStructs
from rdkit.Chem import AllChem
import benchmark as b
from transport import Relay,LongTruncation,dump,sha,functions
ROOT=Path(__file__).resolve().parent
LIBRARIES={}
warnings.filterwarnings('ignore',category=pd.errors.SettingWithCopyWarning)

def init_libraries(method):
 rows=json.loads((ROOT/'reference'/f'{method}.json').read_text())
 db=pd.DataFrame(rows);db['sequence']=db['smiles'];db['SMILES']=db['smiles']
 db['mol']=db['smiles'].map(Chem.MolFromSmiles)
 for sm in db['smiles']:b.fingerprint(sm)
 LIBRARIES[method]=db

def chatdrug(case,relay,out):
 db=LIBRARIES['chatdrug'];targets=b.constraints(case);state={'selected':None,'generations':0,'retrieval_calls':[]}
 parser=functions(ROOT/'source/chatdrug_parser.py',['parse_molecule'],{'re':re})['parse_molecule']
 lookup=db.set_index('smiles').to_dict('index') if not db['smiles'].duplicated().any() else {row['smiles']:row for row in db.to_dict('records')}
 def complete(messages,*args):
  state['generations']+=1
  return relay.complete(messages,f'chatdrug/{state["generations"]}')
 def parse(task,inp,text,ref):
  candidates=parser(inp,text,ref);state['selected']=candidates[0] if candidates else None
  return candidates
 def evaluate(inp,sm,*args,**kwargs):
  if not b.mol_prop(sm,'validity'):return -1
  return b.evaluate(case,sm)['success']
 def reference_eval(inp,sm,*args,**kwargs):
  return all(lookup[sm][k]==v for k,v in targets.items())
 def similarity(task,a,c):return DataStructs.TanimotoSimilarity(b.fingerprint(a),b.fingerprint(c))
 retrieval=functions(ROOT/'source/chatdrug_utils.py',['retrieve_and_feedback'],{'sim_sequence':similarity,'evaluate':reference_eval})['retrieve_and_feedback']
 def retrieve(*args):
  event={'eligible_references':int(sum(all(row[k]==v for k,v in targets.items()) for row in lookup.values()))}
  state['retrieval_calls'].append(event)
  try:
   value=retrieval(*args);event['reference']=value;return value
  except Exception as e:event['error_type']=type(e).__name__;raise
 ns={'sys':sys,'complete':complete,'parse':parse,'evaluate':evaluate,'retrieve_and_feedback':retrieve}
 functions(ROOT/'source/chatdrug_main.py',['conversation','ReDF'],ns)
 parent=case['smiles'];record={parent:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
 messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':case['instruction']+' Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.'}]
 log=io.StringIO()
 for i in range(3):
  answer,candidate=ns['conversation'](messages,None,None,'chatgpt',2,i,0,101,'molecule',parent,db,record,log,False,'s2_exact',{},None,None)
  if answer!=0 or candidate is None:break
 dump(out/'trace.json',{'record':record,'messages':messages,'state':state,'native_answer':answer,'native_return':candidate})
 return state['selected'],{'generation_calls':state['generations'],'max_generations':3,'native_answer':answer,'retrieval_calls':state['retrieval_calls']}

def agentdrug(case,relay,out):
 targets=b.constraints(case);db=LIBRARIES['agentdrug'];feedbacks=[];predictions=[]
 mask=pd.Series(True,index=db.index)
 for key,value in targets.items():mask &= db[key]==value
 eligible=db.loc[mask].copy()
 def feedback(sm,dataset):
  score=b.evaluate(case,sm)
  detail='; '.join(f'{k}: actual {score["actual"][k]}, required {v}' for k,v in targets.items())
  text='The generated molecule does not satisfy the required counts. '+detail+'.'
  feedbacks.append({'candidate':sm,'score':score,'eligible_references':len(eligible)})
  return score['success'],eligible.copy(),text
 ns={'Chem':Chem,'AllChem':AllChem,'DataStructs':DataStructs,'s2_feedback':feedback,
     'get_validity_feedback':lambda sm,_:'The modified molecule is chemically valid.' if b.mol_prop(sm,'validity') else 'The modified molecule is not chemically valid.',
     'listize_fn':lambda batch:{k:[v] for k,v in batch.items()}}
 exec(compile((ROOT/'agentdrug_s2_core.py').read_text(),str(ROOT/'agentdrug_s2_core.py'),'exec'),ns)
 class Model:
  def inference(self,batch):
   text=relay.complete([{'role':'user','content':batch['prompt'][0]}],f'agentdrug/{len(predictions)+1}',cap=256).strip()
   predictions.append(text)
   return {'id':batch['id'],'label':batch['smiles'],'pred':[text]}
 # The upstream single/multi iteration defaults map to the count constraints.
 generations=4 if len(targets)==1 else 5
 args=types.SimpleNamespace(data='s2/'+case['subtask'],refine_steps=generations-1)
 prompt=case['instruction']+'\nRespond with only the SMILES string of your molecule. No explanation is needed.\nAnswer:'
 batch={'id':case['id'],'smiles':case['smiles'],'prompt':prompt,'label':None}
 outputs,invalid,steps=ns['run_core'](args,batch,Model(),types.SimpleNamespace(DB=db))
 dump(out/'trace.json',{'predictions':predictions,'feedbacks':feedbacks,'outputs':outputs})
 if len(outputs)!=1:raise RuntimeError('Expected exactly one native final output')
 return outputs[0]['pred'][0],{'generation_calls':len(predictions),'max_generations':generations,'validity_feedback_count':invalid,'core_iterations':steps,'eligible_references':len(eligible)}

def run_case(method,case,stage):
 out=ROOT/'runs'/stage/method/case['id'];out.mkdir(parents=True,exist_ok=True)
 resultpath=out/'result.json'
 if resultpath.exists():return json.loads(resultpath.read_text())
 relay=Relay(out);started=time.time();result={'method':method,'id':case['id'],'task':case['task'],'subtask':case['subtask'],'started':started,'case':case}
 try:
  candidate,details=globals()[method](case,relay,out)
  result.update(status='complete',candidate=candidate,score=b.evaluate(case,candidate),**details)
 except LongTruncation:result.update(status='error',error='PROVIDER_OUTPUT_TRUNCATED')
 except Exception as e:
  result.update(status='error',error=type(e).__name__)
  (out/'error.txt').write_text(traceback.format_exc())
 result.update(seconds=time.time()-started,usage=relay.usage())
 dump(resultpath,result)
 print(json.dumps({'method':method,'id':case['id'],'status':result['status'],'success':result.get('score',{}).get('success'),'calls':result['usage']['llm_calls'],'error':result.get('error')}),flush=True)
 return result

def summarize(stage,method):
 rows=[json.loads(p.read_text()) for p in (ROOT/'runs'/stage/method).glob('*/result.json')];groups={}
 for r in rows:
  g=groups.setdefault(r['task']+'_'+r['subtask'],{'processed':0,'complete':0,'errors':0,'valid':0,'success':0,'llm_calls':0})
  g['processed']+=1;g['complete']+=r['status']=='complete';g['errors']+=r['status']!='complete'
  g['valid']+=bool(r.get('score',{}).get('valid'));g['success']+=bool(r.get('score',{}).get('success'));g['llm_calls']+=r['usage']['llm_calls']
 summary={'method':method,'stage':stage,'processed':len(rows),'groups':groups,'errors':[{'id':r['id'],'error':r['error']} for r in rows if r['status']!='complete'],'updated':time.time()}
 dump(ROOT/'runs'/stage/method/'summary.json',summary);return summary

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);ap.add_argument('method',choices=['chatdrug','agentdrug']);ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
 folder=ROOT/'runs'/args.stage/args.method;folder.mkdir(parents=True,exist_ok=True)
 lock=(folder/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=b.cases()
 if args.stage=='pilot':cases=[c for c in cases if c['row_index']<2]
 else:
  pilot=json.loads((ROOT/'runs/pilot'/args.method/'summary.json').read_text());assert pilot['processed']==12 and not pilot['errors']
 config={'method':args.method,'stage':args.stage,'cases':len(cases),'model':'deepseek-v4.1-flash','provider':'Alibaba Bailian','temperature':0,'thinking':False,'workers':args.workers,'data_manifest_sha256':sha(ROOT/'data/manifest.json'),'source_manifest_sha256':sha(ROOT/'source/manifest.json'),'code_hashes':{p.name:sha(p) for p in ROOT.glob('*.py') if p.name not in ['deploy.py','prepare.py','test_protocol.py']}}
 if (folder/'config.json').exists():assert json.loads((folder/'config.json').read_text())==config
 else:dump(folder/'config.json',config)
 init_libraries(args.method)
 # Interleave all six subtasks rather than hiding later tasks behind one long queue.
 cases.sort(key=lambda c:(c['row_index'],c['task'],c['subtask']))
 with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
  futures={pool.submit(run_case,args.method,c,args.stage):c['id'] for c in cases}
  for future in concurrent.futures.as_completed(futures):future.result();summarize(args.stage,args.method)
 summary=summarize(args.stage,args.method);print(json.dumps(summary),flush=True)
 if summary['errors']:raise SystemExit(2)

if __name__=='__main__':main()
