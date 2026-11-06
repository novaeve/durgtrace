import json,collections
import runner as r

sample=[{'Original block':'CC','Substitute block':'CCC','Rationale':'test'}]
for text in [json.dumps(sample),'```json\n'+json.dumps(sample)+'\n```','```python\n'+repr(sample)+'\n```','Explanation\n'+json.dumps(sample)]:
 assert r.parse_modifications(text)==sample
cases=json.loads((r.benchmark.PREP/'cases.json').read_text())
unique=list(dict.fromkeys(c['smiles'] for c in cases))
counts=collections.Counter();issues=[]
for sm in unique:
 try:
  seq=r.TOKENIZER['get_blocks'](sm)[0].replace('.','^')
  rebuilt=r.TOKENIZER['reconstruct_mol'](seq)
  if r.p.canonical(rebuilt)==r.p.canonical(sm):counts['exact_roundtrip']+=1
  else:
   counts['changed_roundtrip']+=1;issues.append({'input':sm,'rebuilt':rebuilt})
 except Exception as e:
  counts['reconstruction_failure']+=1;issues.append({'input':sm,'error':type(e).__name__})
for task in ['QED','LogP','MR']:
 for trend in ['increase','decrease']:
  prompts=[]
  def call(prompt):prompts.append(prompt);return '```python\n'+repr(sample)+'\n```'
  ns=r.core_namespace(call,lambda sm:('test structure','CC',['CC']))
  fixed=ns['optimize_mol_tomg']('CC',task,trend)
  original=dict(ns);exec((r.ROOT/'core_original.py').read_text(),original)
  expected=original['optimize_mol_tomg']('CC',task,trend)
  assert fixed==expected and prompts[0]==prompts[1]
result={'input_cases':len(cases),'unique_inputs':len(unique),'roundtrip':dict(counts),'issues':issues,'parser_tests':4,'original_core_equivalence_tests':6}
r.dump(r.ROOT/'validation.json',result)
print(json.dumps({k:v for k,v in result.items() if k!='issues'}),flush=True)
