import argparse,concurrent.futures,fcntl,hashlib,json,pathlib,sys,time,types,warnings
ROOT=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/data2/chenfuxin/chatdrug_generalization_20260920')
sys.path.insert(0,str(BASE))
import full_experiment as benchmark
from deepseek_check import config
p=benchmark.p;p.env_config=config
warnings.filterwarnings('ignore',category=p.pd.errors.SettingWithCopyWarning)
Chem=p.Chem;AllChem=p.AllChem;DataStructs=p.DataStructs
CORE=(ROOT/'core_fixed.py').read_text()
CORPUS=None

def dump(path,obj):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.replace(path)

def validity(smiles,_):
 # Same RDKit check/output as utils.py, without string-interpolated Python execution.
 return 'The modified molecule is chemically valid.' if Chem.MolFromSmiles(smiles) is not None else 'The modified molecule is not chemically valid.'

def init_corpus():
 global CORPUS
 if CORPUS is None:
  CORPUS=p.pd.read_csv(benchmark.PREP/'retrieval.csv').rename(columns={'sequence':'SMILES'})
  CORPUS['mol']=CORPUS['SMILES'].apply(Chem.MolFromSmiles)
 return CORPUS

def setup(case,filename='core_fixed.py',small_db=None):
 names=[prop+('+' if direction==1 else '-') for prop,direction in case['objectives']]
 funcs={name:(lambda mol,prop=prop:benchmark.properties(Chem.MolToSmiles(mol,isomericSmiles=True),case['benchmark']=='ChatDrug')[prop]) for name,(prop,_) in zip(names,case['objectives'])}
 thres={name:[list([threshold]),list([threshold])] for name,threshold in zip(names,case['thresholds'])}
 # Cache benchmark-specific descriptor evaluation; source Kekulize behavior is retained.
 db=(init_corpus() if small_db is None else small_db).copy()
 db['prop']=db['mol'].apply(funcs[names[-1]])
 if len(names)>1:db['logp']=db['mol'].apply(funcs[names[0]])
 ns={'Chem':Chem,'AllChem':AllChem,'DataStructs':DataStructs,'task2func':funcs,'task2thres':thres,'get_validity_feedback':validity,'listize_fn':lambda batch:{k:[v] for k,v in batch.items()}}
 exec(compile((ROOT/filename).read_text(),str(ROOT/filename),'exec'),ns)
 args=types.SimpleNamespace(data=('single/' if len(names)==1 else 'multi/')+''.join(names),refine_steps=3 if len(names)==1 else 4,hit_thres=0 if case['constraint']=='loose' else 1)
 prompt=case['instruction']+'\nRespond with only the SMILES string of your modified molecule. No explanation is needed.'
 batch={'id':case['id'],'smiles':case['smiles'],'label':None,'prompt':prompt+'\n\nMolecule:'+case['smiles']+'\nAnswer:'}
 return ns,args,batch,types.SimpleNamespace(DB=db)

class Model:
 def __init__(self,out):self.relay=p.Relay(out/'api_calls.json');self.predictions=[]
 def inference(self,batch):
  try:text=self.relay.complete([{'role':'user','content':batch['prompt'][0]}],'generation_'+str(len(self.predictions)+1),max_tokens=256)
  except p.RelayError as e:
   # Original model.generate returns decoded text even at its 256-token cap.
   # Let RDKit and the original refinement loop handle it, without resampling.
   if str(e)!='OUTPUT_TRUNCATED':raise
   text=self.relay.calls[-1]['output']
  self.predictions.append(text.strip())
  return {'id':batch['id'],'label':batch['smiles'],'pred':[text.strip()]}

def run_case(case,stage):
 out=ROOT/'runs'/stage/case['id'];out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 start=time.monotonic();model=Model(out);r={'id':case['id'],'case':case,'status':'running'}
 try:
  ns,args,batch,dataset=setup(case)
  outputs,validity_work,total_work=ns['run_core'](args,batch,model,dataset)
  if len(outputs)!=1:raise RuntimeError('Core must return exactly one final output')
  candidate=outputs[0]['pred'][0]
  r.update(status='complete',candidate=candidate,score=benchmark.score(case,candidate),generation_calls=len(model.predictions),validity_feedback_count=validity_work,core_iterations=total_work,max_generations=args.refine_steps+1)
 except Exception as e:r.update(status='error',error=str(e) if isinstance(e,p.RelayError) else type(e).__name__,generation_calls=len(model.predictions))
 r['api_requests']=sum(len(x['attempts']) for x in model.relay.calls)
 r['truncated_responses']=sum(x.get('stop_reason')=='max_tokens' for x in model.relay.calls)
 r['seconds']=round(time.monotonic()-start,3)
 r['usage']={k:sum(x.get('usage',{}).get(k,0) or 0 for x in model.relay.calls) for k in ['input_tokens','output_tokens','cache_read_input_tokens']}
 dump(out/'result.json',r);print(json.dumps({'id':r['id'],'status':r['status'],'success':r.get('score',{}).get('success'),'calls':r['generation_calls'],'error':r.get('error')}),flush=True)
 return r

def summarize(stage):
 rows=[json.loads(f.read_text()) for f in (ROOT/'runs'/stage).glob('*/result.json')];groups={}
 for r in rows:
  key='ChatDrug' if r['case']['benchmark']=='ChatDrug' else r['case']['property'];g=groups.setdefault(key,{'complete':0,'error':0,'success':0,'calls':0})
  g['complete' if r['status']=='complete' else 'error']+=1;g['success']+=bool(r.get('score',{}).get('success'));g['calls']+=r['generation_calls']
 summary={'processed':len(rows),'groups':groups,'errors':[{'id':r['id'],'error':r.get('error')} for r in rows if r['status']=='error'],'api_requests':sum(r['api_requests'] for r in rows)}
 dump(ROOT/'runs'/stage/'summary.json',summary);return summary

def main():
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['pilot','full']);args=parser.parse_args()
 out=ROOT/'runs'/args.stage;out.mkdir(parents=True,exist_ok=True)
 lock=(out/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=json.loads((benchmark.PREP/'cases.json').read_text())
 if args.stage=='pilot':
  buckets={}
  for c in cases:buckets.setdefault((c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction']),c)
  cases=list(buckets.values());assert len(cases)==34
 else:
  gate=json.loads((ROOT/'runs/pilot/summary.json').read_text());assert gate['processed']==34 and not gate['errors']
 hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['runner.py','core_fixed.py','core_original.py']}
 manifest={'stage':args.stage,'expected':len(cases),'case_ids':[c['id'] for c in cases],'model':'deepseek-flash','temperature':0,'thinking':'disabled','max_tokens':256,'cap_source':'upstream/source/config.py max_completion_length=256','generations':'upstream 4 single/5 multi','workers':2,'retrieval_sha256':p.sha(benchmark.PREP/'retrieval.csv'),'test_manifest_sha256':p.sha(benchmark.PREP/'manifest.json'),'code_hashes':hashes}
 manifestpath=out/'run_config.json'
 if manifestpath.exists():assert json.loads(manifestpath.read_text())['code_hashes']==hashes
 else:dump(manifestpath,manifest)
 init_corpus()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  pending=iter(cases);jobs={}
  for _ in range(2):
   c=next(pending,None)
   if c:jobs[pool.submit(run_case,c,args.stage)]=c['id']
  while jobs:
   done,_=concurrent.futures.wait(jobs,return_when=concurrent.futures.FIRST_COMPLETED)
   for future in done:
    future.result();del jobs[future];summarize(args.stage)
    c=next(pending,None)
    if c:jobs[pool.submit(run_case,c,args.stage)]=c['id']
 summary=summarize(args.stage);print(json.dumps(summary),flush=True)
 if summary['errors']:raise SystemExit(2)

if __name__=='__main__':main()
