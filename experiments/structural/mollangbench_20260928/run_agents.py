"""Original generation/refinement/retrieval loops + public instruction checks."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import argparse,concurrent.futures,fcntl,io,json,re,sys,time,types,traceback
import pandas as pd
from rdkit import Chem,DataStructs,RDLogger
from rdkit.Chem import AllChem
from transport import Relay,LongTruncation,dump,sha,functions
import public_checks as checks
RDLogger.DisableLog('rdApp.*')
ROOT=Path(__file__).resolve().parent
LIBS={};PLANS={}

def public_prompt(case,method):
 phrase='Return the resulting SMILES string enclosed within <smiles> and </smiles> tags.'
 assert case['prompt'].count(phrase)==1
 requirement=('Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.' if method=='chatdrug' else 'Respond with only the SMILES string of your molecule. No explanation is needed.')
 return case['prompt'].replace(phrase,requirement)

def init(method):
 global PLANS
 PLANS=json.loads((ROOT/'checks/plans.json').read_text())
 assert json.loads((ROOT/'checks/manifest.json').read_text())['checks_code_sha256']==sha(ROOT/'public_checks.py')
 rows=json.loads((ROOT/'checks'/f'{method}_library.json').read_text())
 db=pd.DataFrame({'SMILES':[r['smiles'] for r in rows]});db['mol']=db['SMILES'].map(Chem.MolFromSmiles)
 db['fp']=db['mol'].map(lambda m:AllChem.GetMorganFingerprint(m,2))
 LIBS[method]={'db':db,'props':[r['props'] for r in rows]}

def eligible(method,plan):
 rows=LIBS[method]['props']
 mask=[all(checks.compare(checks.value(p,r['property']),r['operator'],r['target']) for r in plan['rules']) for p in rows]
 return LIBS[method]['db'].loc[mask].copy()

def chatdrug(case,relay,out):
 plan=PLANS[case['id']];db=eligible('chatdrug',plan);selected=[];assessments=[];calls=0
 parser=functions(ROOT/'agent_source/chatdrug_parser.py',['parse_molecule'],{'re':re})['parse_molecule']
 def complete(messages,*args):
  nonlocal calls
  calls+=1;return relay.complete(messages,f'chatdrug/{calls}')
 def parse(task,inp,raw,ref):
  values=parser(inp,raw,ref);selected.append(values[0] if values else None);return values
 def evaluate(inp,sm,*args):
  assessment=checks.assess(plan,sm);assessments.append(assessment)
  if not assessment['valid']:return -1
  return assessment['task_status']=='verified_pass'
 def retrieval(*args):
  candidate=args[3]
  # Keep author's all-library sort and first eligible selection, including ties.
  all_db=LIBS['chatdrug']['db'].copy();fp=AllChem.GetMorganFingerprint(Chem.MolFromSmiles(candidate),2)
  all_db['sim']=DataStructs.BulkTanimotoSimilarity(fp,all_db['fp'].tolist())
  eligible_indices=set(db.index)
  for index,row in all_db.sort_values('sim',ascending=False).iterrows():
   if index in eligible_indices:return row['SMILES']
  raise Exception('No reference satisfies implemented public-instruction checks')
 def redf_prompt(candidate,reference):
  return (checks.feedback_text(assessments[-1])+f'\nYour candidate is {candidate}. Reference molecule {reference} is similar and satisfies the implemented checks only; it is not a verified full-task answer. Provide a revised molecule following the original instruction.')
 ns={'sys':sys,'complete':complete,'parse':parse,'evaluate':evaluate,'retrieve_and_feedback':retrieval,'public_redf_prompt':redf_prompt}
 functions(ROOT/'agent_source/chatdrug_main.py',['conversation','ReDF'],ns)
 # Only feedback wording changes: partial correctness must not be called correct.
 import ast
 tree=ast.parse((ROOT/'agent_source/chatdrug_main.py').read_text())
 redf=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='ReDF')
 class ReplacePrompt(ast.NodeTransformer):
  def visit_Assign(self,node):
   if any(isinstance(t,ast.Name) and t.id=='prompt_ReDF' for t in node.targets):
    node.value=ast.Call(func=ast.Name(id='public_redf_prompt',ctx=ast.Load()),args=[ast.Name(id='generated_drug',ctx=ast.Load()),ast.Name(id='closest_drug',ctx=ast.Load())],keywords=[])
   return node
 redf=ReplacePrompt().visit(redf);exec(compile(ast.fix_missing_locations(ast.Module(body=[redf],type_ignores=[])),'<chatdrug_public_feedback>','exec'),ns)
 parent=case.get('original_smiles');record={parent:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
 messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':public_prompt(case,'chatdrug')}]
 log=io.StringIO()
 for round_index in range(3):
  answer,candidate=ns['conversation'](messages,None,None,'chatgpt',2,round_index,0,101,'molecule',parent,None,record,log,False,None,{},None,None)
  if answer!=0 or candidate is None:break
 state={'generation_calls':calls,'max_generations':3,'eligible_references':len(db),'complete_task_verifier':plan['complete_task_verifier'],'native_answer':answer,'task_status':assessments[-1]['task_status'] if assessments else 'no_parse','feedback_scope':'public instruction checks only'}
 dump(out/'trace.json',{'state':state,'plan':plan,'messages':messages,'record':record,'assessments':assessments})
 return selected[-1] if selected else None,state

def agentdrug(case,relay,out):
 plan=PLANS[case['id']];db=eligible('agentdrug',plan);predictions=[];assessments=[]
 def public_feedback(sm):
  a=checks.assess(plan,sm);assessments.append(a);return a,db.copy(),checks.feedback_text(a)
 ns={'Chem':Chem,'AllChem':AllChem,'DataStructs':DataStructs,'public_feedback':public_feedback,
     'get_validity_feedback':lambda sm,_:'The modified molecule is chemically valid.' if Chem.MolFromSmiles(sm) is not None else 'The modified molecule is not chemically valid.',
     'listize_fn':lambda batch:{k:[v] for k,v in batch.items()}}
 exec(compile((ROOT/'agent_source/agentdrug_public_feedback.py').read_text(),'<agentdrug_public_feedback>','exec'),ns)
 class Model:
  def inference(self,batch):
   value=relay.complete([{'role':'user','content':batch['prompt'][0]}],f'agentdrug/{len(predictions)+1}',cap=256).strip();predictions.append(value)
   return {'id':batch['id'],'label':batch['smiles'],'pred':[value]}
 maximum=4 if case['task']=='edit' else 5
 args=types.SimpleNamespace(data='public_instruction/'+case['task'],refine_steps=maximum-1)
 batch={'id':case['id'],'smiles':case.get('original_smiles'),'prompt':public_prompt(case,'agentdrug')+'\nAnswer:','label':None}
 outputs,invalid,steps=ns['run_core'](args,batch,Model(),None)
 assert len(outputs)==1
 state={'generation_calls':len(predictions),'max_generations':maximum,'validity_feedback_count':invalid,'core_iterations':steps,'eligible_references':len(db),'complete_task_verifier':plan['complete_task_verifier'],'feedback_scope':'public instruction checks only'}
 dump(out/'trace.json',{'state':state,'plan':plan,'predictions':predictions,'assessments':assessments,'outputs':outputs})
 return outputs[0]['pred'][0],state

def job(method,case,stage):
 out=ROOT/'runs'/stage/method/case['id'];out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 start=time.time();relay=Relay(out)
 row={'method':method,'variant':'public_instruction_feedback','id':case['id'],'task':case['task'],'split':case['split'],'index':case['index'],'started':start}
 try:
  candidate,details=globals()[method](case,relay,out);row.update(status='complete',candidate=candidate,output='<smiles>'+(candidate or '')+'</smiles>',details=details)
 except LongTruncation:row.update(status='error',error='PROVIDER_OUTPUT_TRUNCATED',candidate=None,output='')
 except Exception as e:
  row.update(status='error',error=type(e).__name__,candidate=None,output='');(out/'error.txt').write_text(traceback.format_exc())
 row.update(ended=time.time(),seconds=time.time()-start,usage=relay.usage())
 dump(out/'result.json',row);print(json.dumps({'method':method,'id':case['id'],'status':row['status'],'calls':row['usage']['llm_calls'],'error':row.get('error')}),flush=True)
 return row

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);ap.add_argument('method',choices=['chatdrug','agentdrug']);a=ap.parse_args()
 folder=ROOT/'runs'/a.stage/a.method;folder.mkdir(parents=True,exist_ok=True)
 lock=(folder/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=json.loads((ROOT/'data/cases.json').read_text())
 if a.stage=='pilot':cases=[c for c in cases if c['index']<2]
 else:
  pilot=[json.loads(p.read_text()) for p in (ROOT/'runs/pilot'/a.method).glob('*/result.json')]
  assert len(pilot)==8 and all(r['status']=='complete' or r.get('error')=='PROVIDER_OUTPUT_TRUNCATED' for r in pilot)
 config={'method':a.method,'variant':'public_instruction_feedback','model':'deepseek-v4.1-flash','temperature':0,'thinking':False,'gold_access':False,'workers':4,'expected':len(cases),'manifest_sha256':sha(ROOT/'data/experiment_manifest.json'),'checks_manifest_sha256':sha(ROOT/'checks/manifest.json'),'code_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'run_agents.py',ROOT/'public_checks.py',ROOT/'transport.py',*(ROOT/'agent_source').glob('*.py')]}}
 cp=folder/'config.json'
 if cp.exists():assert json.loads(cp.read_text())==config
 else:dump(cp,config)
 init(a.method)
 rows={r['id']:r for p in folder.glob('*/result.json') for r in [json.loads(p.read_text())]}
 pending=[c for c in cases if c['id'] not in rows];pending.sort(key=lambda c:(c['index'],c['task'],c['split']))
 def summary():
  d={'processed':len(rows),'expected':len(cases),'runtime_errors':sum(r['status']!='complete' for r in rows.values()),'updated':time.time(),'variant':'public_instruction_feedback'}
  dump(folder/'summary.json',d);return d
 with concurrent.futures.ThreadPoolExecutor(4) as pool:
  fs=[pool.submit(job,a.method,c,a.stage) for c in pending]
  for f in concurrent.futures.as_completed(fs):r=f.result();rows[r['id']]=r;summary()
 print(json.dumps(summary()),flush=True)
if __name__=='__main__':main()
