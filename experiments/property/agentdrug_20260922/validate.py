import json,types
import runner as r
r.init_corpus();small=r.CORPUS.iloc[:30].copy()
cases=json.loads((r.benchmark.PREP/'cases.json').read_text());buckets={}
for c in cases:buckets.setdefault((c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction']),c)
class Scripted:
 def __init__(self,sequence):self.sequence=sequence;self.prompts=[]
 def inference(self,batch):
  self.prompts.append(batch['prompt'][0]);text=self.sequence[min(len(self.prompts)-1,len(self.sequence)-1)]
  return {'id':batch['id'],'label':batch['smiles'],'pred':[text]}
checks=0
for c in buckets.values():
 ns,args,batch,ds=r.setup(c,small_db=small)
 names=[p+('+' if d==1 else '-') for p,d in c['objectives']]
 for s in small.SMILES:
  mol=r.Chem.MolFromSmiles(s);orig=r.Chem.MolFromSmiles(c['smiles'])
  hit=all((ns['task2func'][n](mol)>ns['task2func'][n](orig)+t if d==1 else ns['task2func'][n](mol)+t<ns['task2func'][n](orig)) for n,(_,d),t in zip(names,c['objectives'],c['thresholds']))
  assert hit==r.benchmark.score(c,s)['success'],(c['id'],s)
  checks+=1
 model=Scripted([c['smiles']]);out,_,work=ns['run_core'](args,batch,model,ds)
 assert len(out)==1 and len(model.prompts)==(4 if len(names)==1 else 5)
 # Every inserted reference satisfies ALL benchmark objectives, with no arbitrary similarity threshold.
 for prompt in model.prompts:
  if 'For your reference, we find a molecule ' in prompt:
   ref=prompt.split('For your reference, we find a molecule ')[1].split(' which is correct')[0]
   assert r.benchmark.score(c,ref)['success'],(c['id'],ref)
c=cases[0];ns,args,batch,ds=r.setup(c,small_db=small)
model=Scripted(['not_a_smiles',c['smiles']]);ns['run_core'](args,batch,model,ds)
assert 'not chemically valid' in model.prompts[1]
# Compare untouched prompt/selection behavior against original core on valid single-property and positive multi-property branches.
parity=0
for c in [next(x for x in cases if x['task']==102),next(x for x in cases if x['task']==202)]:
 outputs=[]
 for filename in ['core_original.py','core_fixed.py']:
  ns,args,batch,ds=r.setup(c,filename,small_db=small);args.refine_steps=1
  model=Scripted([c['smiles']]);out,_,_=ns['run_core'](args,batch,model,ds);outputs.append((out,model.prompts))
 assert outputs[0]==outputs[1],c['id'];parity+=1
result={'passed':True,'score_equivalence_checks':checks,'coverage_settings':len(buckets),'validity_feedback_fix':True,'loop_limits_checked':True,'retrieved_references_satisfy_all_conditions':True,'original_core_parity_scenarios':parity}
r.dump(r.ROOT/'validation.json',result);print(json.dumps(result),flush=True)
