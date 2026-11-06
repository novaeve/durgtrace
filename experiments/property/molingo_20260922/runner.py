import argparse,ast,collections,concurrent.futures,fcntl,hashlib,inspect,itertools,json,pathlib,re,sys,threading,time,types
import numpy as np
import pandas as pd
import requests
ROOT=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/data2/chenfuxin/chatdrug_generalization_20260920');sys.path.insert(0,str(BASE))
import full_experiment as benchmark
from deepseek_check import config
p=benchmark.p;p.env_config=config
Chem=p.Chem
# Preserve transport behavior while omitting the ChatDrug runner's added max_tokens cap.
relay_source=inspect.getsource(p.Relay).replace("'max_tokens':max_tokens,",'',1).replace("'max_tokens':max_tokens","'max_tokens':None,'cap_policy':'provider default'")
relay_ns=dict(p.__dict__);exec(relay_source,relay_ns);Relay=relay_ns['Relay']
NAMES={};NAME_LOCK=threading.Lock();STRUCTURE_LOCK=threading.Lock();STRUCTURES={}
CACHE=ROOT/'cache';CACHE.mkdir(exist_ok=True)
if (CACHE/'names.json').exists():NAMES=json.loads((CACHE/'names.json').read_text())

def dump(path,obj):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.replace(path)

class PubChem:
 @staticmethod
 def get_compounds(smiles,_):
  with NAME_LOCK:
   if smiles not in NAMES:
    try:
     response=requests.get('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/'+requests.utils.quote(smiles,safe='')+'/synonyms/JSON',timeout=(5,10))
     response.raise_for_status();data=response.json()['InformationList']['Information'][0].get('Synonym',[])
     NAMES[smiles]={'synonyms':data[:1],'status':'ok'}
    except Exception as e:NAMES[smiles]={'status':'lookup_failure','error_type':type(e).__name__}
    dump(CACHE/'names.json',NAMES)
   row=NAMES[smiles]
   if row['status']!='ok':raise RuntimeError('PUBCHEM_LOOKUP_FAILED')
   return [types.SimpleNamespace(synonyms=row['synonyms'])] if row['synonyms'] else []

def load_tokenizer():
 ns={'__name__':'molingo_tokenizer','pcp':PubChem,'print':lambda *a,**k:None}
 for filename in ['drug_like_filtering.py','tokenizer.py']:
  tree=ast.parse((ROOT/'upstream/toolset'/filename).read_text());nodes=[]
  for n in tree.body:
   if isinstance(n,ast.FunctionDef):nodes.append(n)
   elif isinstance(n,(ast.Import,ast.ImportFrom)):
    text=ast.unparse(n)
    if 'pubchempy' not in text and 'toolset.' not in text:nodes.append(n)
  exec(compile(ast.Module(body=nodes,type_ignores=[]),filename,'exec'),ns)
 ns['vocab']=json.loads((ROOT/'upstream/toolset/vocab20.json').read_text());ns['vocab_sm']=set(ns['vocab'])
 return ns

TOKENIZER=load_tokenizer()

def structure(smiles):
 # Shared cache uses the same deterministic decomposition across settings of a molecule.
 with STRUCTURE_LOCK:
  if smiles in STRUCTURES:return STRUCTURES[smiles]
  key=hashlib.sha256(smiles.encode()).hexdigest();path=CACHE/'structures'/f'{key}.json'
  if path.exists():value=json.loads(path.read_text())['value']
  else:
   value=TOKENIZER['smiles2NLdesc'](smiles)
   dump(path,{'smiles':smiles,'value':value})
  STRUCTURES[smiles]=value;return value

def parse_modifications(text):
 candidates=[text.strip()]
 candidates+=re.findall(r'```(?:json|python)?\s*(.*?)```',text,re.S)
 for start,c in enumerate(text):
  if c!='[':continue
  try:obj,end=json.JSONDecoder().raw_decode(text[start:]);candidates.append(text[start:start+end])
  except ValueError:pass
 for candidate in candidates:
  obj=None
  for parse in [json.loads,ast.literal_eval]:
   try:obj=parse(candidate);break
   except (ValueError,SyntaxError,TypeError):continue
  if isinstance(obj,list) and all(isinstance(x,dict) and all(isinstance(x.get(k),str) for k in ['Original block','Substitute block']) for x in obj):return obj
 raise ValueError('MODEL_MODIFICATION_LIST_UNPARSEABLE')

def core_namespace(call,structure_fn=structure):
 ns={'literal_eval':ast.literal_eval,'product':itertools.product,'np':np,'smiles2NLdesc':structure_fn,'s2m':Chem.MolFromSmiles,'reconstruct_mol':TOKENIZER['reconstruct_mol'],'gpt_api':call,'parse_modifications':parse_modifications,'print':lambda *a,**k:None}
 exec(compile((ROOT/'core_fixed.py').read_text(),str(ROOT/'core_fixed.py'),'exec'),ns)
 return ns

def run_case(case,stage):
 out=ROOT/'runs'/stage/case['id'];out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 relay=Relay(out/'api_calls.json');start=time.monotonic();r={'id':case['id'],'case':case,'status':'running'}
 def call(prompt):
  try:return relay.complete([{'role':'user','content':prompt}],'block_substitution')
  except p.RelayError as e:
   if str(e)!='OUTPUT_TRUNCATED':raise
   return relay.calls[-1]['output']
 try:
  ns=core_namespace(call);candidates=ns['optimize_mol_tomg'](case['smiles'],main_task=case['property'],trend='increase' if case['objectives'][0][1]==1 else 'decrease',variants=3,task_instruction=case['instruction'])
  # The provided MolOpt entry returns a set of candidates, with no final selector.
  # Report first valid output and oracle-selected pool result separately.
  scored=[];seen=set()
  for candidate in candidates:
   if not isinstance(candidate,str):continue
   canonical=p.canonical(candidate)
   if canonical is None or canonical in seen:continue
   seen.add(canonical);scored.append(benchmark.score(case,candidate))
  original=p.canonical(case['smiles'])
  blocks=structure(case['smiles'])[2]
  control=benchmark.score(case,TOKENIZER['reconstruct_mol']('^'.join(blocks)))
  r.update(no_modification_control=control,roundtrip_changed=p.canonical(control['candidate'])!=original)
  edited=[x for x in scored if p.canonical(x['candidate'])!=original]
  first=edited[0] if edited else benchmark.score(case,case['smiles'])
  best=max(scored,key=lambda x:(x['success'],x['similarity'] if x['similarity'] is not None else -1),default=benchmark.score(case,None))
  r.update(status='complete',first=first,best=best,candidate_set_success=any(x['success'] for x in scored),candidate_count_raw=len(candidates),candidate_count_valid_unique=len(scored),edited_count=len(edited),candidates=scored)
 except ValueError as e:
  if str(e)!='MODEL_MODIFICATION_LIST_UNPARSEABLE':r.update(status='error',error_type=type(e).__name__)
  else:r.update(status='complete',model_output_failure=str(e),candidate_set_success=False,first=benchmark.score(case,None),best=benchmark.score(case,None),candidate_count_raw=0,candidate_count_valid_unique=0,edited_count=0,candidates=[])
 except Exception as e:r.update(status='error',error=str(e) if isinstance(e,p.RelayError) else type(e).__name__)
 r['api_requests']=sum(len(x['attempts']) for x in relay.calls);r['llm_calls']=len(relay.calls);r['seconds']=round(time.monotonic()-start,3)
 r['truncated_responses']=sum(x.get('stop_reason')=='max_tokens' for x in relay.calls)
 r['usage']={k:sum(x.get('usage',{}).get(k,0) or 0 for x in relay.calls) for k in ['input_tokens','output_tokens','cache_read_input_tokens']}
 dump(out/'result.json',r);print(json.dumps({'id':r['id'],'status':r['status'],'set_success':r.get('candidate_set_success'),'first_success':r.get('first',{}).get('success'),'candidates':r.get('candidate_count_valid_unique'),'error':r.get('error',r.get('error_type'))}),flush=True)
 return r

def summarize(stage):
 rows=[json.loads(f.read_text()) for f in (ROOT/'runs'/stage).glob('*/result.json')];groups={}
 for r in rows:
  key='ChatDrug' if r['case']['benchmark']=='ChatDrug' else r['case']['property'];g=groups.setdefault(key,{'complete':0,'error':0,'candidate_set_success':0,'first_success':0,'llm_calls':0,'model_output_failures':0})
  g['complete' if r['status']=='complete' else 'error']+=1;g['candidate_set_success']+=bool(r.get('candidate_set_success'));g['first_success']+=bool(r.get('first',{}).get('success'));g['llm_calls']+=r['llm_calls'];g['model_output_failures']+=bool(r.get('model_output_failure'))
 result={'processed':len(rows),'groups':groups,'errors':[{'id':r['id'],'error':r.get('error',r.get('error_type'))} for r in rows if r['status']=='error'],'api_requests':sum(r['api_requests'] for r in rows)}
 dump(ROOT/'runs'/stage/'summary.json',result);return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);args=ap.parse_args();stage=args.stage
 out=ROOT/'runs'/stage;out.mkdir(parents=True,exist_ok=True)
 lock=(out/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=json.loads((benchmark.PREP/'cases.json').read_text())
 if stage=='pilot':
  buckets={}
  for c in cases:buckets.setdefault((c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction']),c)
  cases=list(buckets.values());assert len(cases)==34
 else:
  gate=json.loads((ROOT/'runs/pilot/summary.json').read_text());assert gate['processed']==34 and not gate['errors']
 hashes={n:p.sha(ROOT/n) for n in ['runner.py','core_fixed.py','core_original.py']}
 cfg={'model':'deepseek-flash','thinking':'disabled','temperature':0,'max_tokens':'omitted, provider default','workers':2,'modifications_requested':3,'method':'provided optimize_mol_tomg with block assembly','scoring':'first changed valid candidate and candidate-set oracle success separately','input_manifest':p.sha(benchmark.PREP/'manifest.json'),'archive_sha256':'c647dba6c74b8b5b6ac9aab5460fe322fe4b5228068e24c3bbb5a0349d748c37','code_hashes':hashes,'expected':len(cases)}
 cf=out/'run_config.json'
 if cf.exists():assert json.loads(cf.read_text())['code_hashes']==hashes
 else:dump(cf,cfg)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  iterator=iter(cases);jobs={}
  for _ in range(2):
   c=next(iterator,None)
   if c:jobs[pool.submit(run_case,c,stage)]=c['id']
  while jobs:
   done,_=concurrent.futures.wait(jobs,return_when=concurrent.futures.FIRST_COMPLETED)
   for job in done:
    job.result();del jobs[job];summarize(stage);c=next(iterator,None)
    if c:jobs[pool.submit(run_case,c,stage)]=c['id']
 result=summarize(stage);print(json.dumps(result),flush=True)
 if result['errors']:raise SystemExit(2)

if __name__=='__main__':main()
