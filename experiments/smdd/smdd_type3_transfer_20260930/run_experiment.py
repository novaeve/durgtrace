from pathlib import Path
import os,sys,json,time,types,io,ast,argparse,hashlib,traceback,fcntl,re
import yaml
from runtime import ROOT,API,dump,baseline,isolated
from agent_harness.obfuscate import obfuscate_task

def functions(path,names,ns):
 nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
 assert len(nodes)==len(names)
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)

def extract_smiles(text):
 text=text.strip()
 if '```' in text:
  blocks=re.findall(r'```(?:smiles|smi|text)?\s*\n?(.*?)```',text,re.S|re.I)
  if blocks:text=blocks[-1].strip()
 lines=[x.strip() for x in text.splitlines() if x.strip()]
 if not lines:return ''
 return lines[-1].removeprefix('SMILES:').strip().strip('`')

def validity(smiles,out):
 work=out/'validity';work.mkdir(exist_ok=True)
 (work/'input.json').write_text(json.dumps(smiles))
 script="import json; from rdkit import Chem; from rdkit import RDLogger; RDLogger.DisableLog('rdApp.*'); s=json.load(open('input.json')); m=Chem.MolFromSmiles(s) if s else None; print(json.dumps({'valid':m is not None and m.GetNumAtoms()>0}))"
 text,rc=isolated(['python','-c',script],work,60)
 if rc:raise RuntimeError('Validity runtime failed: '+text[-300:])
 return json.loads(text.strip())['valid']

def prompt(task,public):
 s=task['description']+'\n\nComplete public input files follow.\n'
 for name in ['complex.pdb','reference.sdf']:
  s+=f'\n<file name="{name}">\n'+(public/name).read_text()+f'\n</file>\n'
 return s+'\nRespond with only the single SMILES string to put in solution.smi. No explanation is needed.\nAnswer:'

def chatdrug(task,public,out):
 api=API(out);selected=[]
 def complete(messages,*args):return api.complete(messages,cap=32768)['choices'][0]['message']['content'] or ''
 def parse(*args):
  s=extract_smiles(args[2]);selected.append(s);return [s] if s else []
 def evaluate(inp,s,*args):return None if validity(s,out) else -1
 def retrieval(*args):raise Exception('No verified scaffold-hopping reference library; full task correctness is unknown')
 ns={'sys':sys,'complete':complete,'parse':parse,'evaluate':evaluate,'retrieve_and_feedback':retrieval}
 functions(ROOT/'agent_source/chatdrug_main.py',['conversation','ReDF'],ns)
 record={None:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
 messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':prompt(task,public)}]
 log=io.StringIO()
 for i in range(3):
  answer,candidate=ns['conversation'](messages,None,None,'chatgpt',2,i,0,101,'molecule',None,None,record,log,False,None,{},None,None)
  if answer!=0 or candidate is None:break
 pred=selected[-1] if selected else '';(out/'solution.smi').write_text(pred+'\n')
 state={'calls':api.calls,'max_generations':3,'format_valid':validity(pred,out),'stop_reason':'native_reference_unavailable_or_validity_exit','tokens':api.total_tokens,'task_correctness':'unknown'}
 dump(out/'trace.json',{'state':state,'messages':messages,'record':record,'log':log.getvalue()});return state

def agentdrug(task,public,out):
 api=API(out);preds=[]
 source=(ROOT/'agent_source/agentdrug_core.py').read_text()
 start=source.index('                    input_mol = Chem.MolFromSmiles');end=source.index('            except:\n                continue',start)
 source=source[:start]+'''                    feedback_output = "Validity:\\n{}\\nScaffold-hopping task correctness is unknown; no verified reference molecule is available.".format(validity_feedback)
'''+source[end:]
 ns={'get_validity_feedback':lambda s,_:'The modified molecule is chemically valid.' if validity(s,out) else 'The modified molecule is not chemically valid.','listize_fn':lambda b:{k:[v] for k,v in b.items()}}
 exec(compile(source,'<agentdrug_type3_validity_adapter>','exec'),ns)
 class Model:
  def inference(self,b):
   data=api.complete([{'role':'user','content':b['prompt'][0]}],cap=32768)
   value=extract_smiles(data['choices'][0]['message']['content'] or '');preds.append(value)
   return {'id':b['id'],'label':b['smiles'],'pred':[value]}
 args=types.SimpleNamespace(data='type3/scaffold_hopping',refine_steps=3)
 batch={'id':task['id'],'smiles':None,'prompt':prompt(task,public),'label':None}
 outputs,invalid,steps=ns['run_core'](args,batch,Model(),None)
 assert len(outputs)==1
 pred=outputs[0]['pred'][0];(out/'solution.smi').write_text(pred+'\n')
 state={'calls':api.calls,'max_generations':4,'format_valid':validity(pred,out),'validity_feedback_count':invalid,'tokens':api.total_tokens,'task_correctness':'unknown'}
 dump(out/'trace.json',{'state':state,'predictions':preds,'outputs':outputs});return state

def guard(event,args):
 if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
  s=os.fsdecode(args[0]).replace('\\','/')
  if any(v in s for v in ['ground_truth','witness','/gt_results/']):raise PermissionError('Scoring-only file forbidden during inference')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('method',choices=['deepseek','chatdrug','agentdrug']);ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
 (ROOT/'runs'/a.method).mkdir(parents=True,exist_ok=True)
 lock=(ROOT/'runs'/a.method/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 sys.addaudithook(guard)
 ids=[s.strip() for s in (ROOT/'task_list.txt').read_text().splitlines() if s.strip()]
 assert len(ids)==52
 if a.pilot:ids=ids[:1]
 for index,tid in enumerate(ids):
  out=ROOT/'runs'/a.method/tid;out.mkdir(parents=True,exist_ok=True)
  if (out/'result.json').exists():
   r=json.loads((out/'result.json').read_text())
   if r['status']=='error':raise RuntimeError('Existing infrastructure failure needs inspection')
   continue
  full=yaml.safe_load((ROOT/'tasks'/tid/'task.yaml').read_text())
  task={'id':f'task_{index:03d}','description':full['description'],'input_files':full['input_files'],'output_config':full['output_config']}
  public=Path(obfuscate_task(str(ROOT/'tasks'/tid),task['id']))
  assert set(p.name for p in public.iterdir())=={'complex.pdb','reference.sdf'}
  start=time.time();dump(out/'started.json',{'task':tid,'method':a.method,'started':start})
  try:
   details=baseline(task,public,out) if a.method=='deepseek' else globals()[a.method](task,public,out)
   result={'status':details.get('status','complete'),'details':details}
  except Exception as e:
   result={'status':'error','error':type(e).__name__+': '+str(e)};(out/'error.log').write_text(traceback.format_exc())
  result.update(method=a.method,task=tid,started=start,ended=time.time(),seconds=time.time()-start,public_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in public.iterdir()})
  dump(out/'result.json',result);print(json.dumps(result),flush=True)
  if result['status']=='error':raise RuntimeError('Infrastructure/API failure; stopped for inspection')
if __name__=='__main__':main()
