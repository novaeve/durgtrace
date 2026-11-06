"""Compare task decisions against actual upstream evaluator AST, then fake native loops."""
import ast,contextlib,io,json,types,tempfile
from pathlib import Path
import pandas as pd
import benchmark as b
import runner
from transport import dump
ROOT=Path(__file__).resolve().parent

def test_official():
 tree=ast.parse((ROOT/'source/s2_evaluate.py').read_text())
 node=next(n for n in tree.body if isinstance(n,ast.If) and ast.unparse(n.test)=="args.benchmark == 'open_generation'")
 checked=0
 for key in sorted({(c['task'],c['subtask']) for c in b.cases()}):
  cases=[c for c in b.cases() if (c['task'],c['subtask'])==key]
  outputs=[c['smiles'] if c['smiles'] and i%3==0 else ['CCO','invalid','CC(=O)c1ccccc1','CCCCCCCCCCCCCSSC'][i%4] for i,c in enumerate(cases)]
  rows=[dict(c['row']) for c in cases]
  for row in rows:
   if 'benzene_ring' in row:row['benzene rings']=row['benzene_ring']
  ns={'args':types.SimpleNamespace(benchmark='open_generation',task=key[0],subtask=key[1],calc_novelty=False),'data':rows,'data_len':len(rows),'target':pd.DataFrame({'outputs':outputs}),'mol_prop':b.mol_prop,'calculate_similarity':b.calculate_similarity,'tqdm':lambda x:x}
  with contextlib.redirect_stdout(io.StringIO()):exec(compile(ast.Module(body=[node],type_ignores=[]),'official_s2_evaluate','exec'),ns)
  expected=ns['successed'] if key[0]=='MolEdit' else ns['flags']
  actual=[b.evaluate(c,s)['success'] for c,s in zip(cases,outputs)]
  assert actual==[bool(x) for x in expected],key
  checked+=len(cases)
 # Explicit official BondNum zero omission: CCO has two singles, no restriction on zeros.
 c={'task':'MolCustom','subtask':'BondNum','row':dict(single='2',double='0',triple='0',rotatable='0',aromatic='0')}
 assert b.evaluate(c,'CCO')['success']
 return checked

class FakeRelay:
 def __init__(self,outputs):self.outputs=iter(outputs);self.calls=[]
 def complete(self,messages,label,cap=None):
  self.calls.append({'messages':json.loads(json.dumps(messages)),'label':label,'cap':cap})
  return next(self.outputs)

def test_native():
 case=next(c for c in b.cases() if c['subtask']=='AtomNum')
 correct='C'*13+'SS'
 assert b.evaluate(case,correct)['success']
 for method in ['chatdrug','agentdrug']:
  runner.init_libraries(method)
  with tempfile.TemporaryDirectory() as folder:
   out=Path(folder)
   relay=FakeRelay([('- '+correct) if method=='chatdrug' else correct])
   candidate,detail=getattr(runner,method)(case,relay,out)
   assert b.evaluate(case,candidate)['success'] and len(relay.calls)==1
   # No hidden initialization: first user message contains the unaltered official instruction.
   assert case['instruction'] in relay.calls[0]['messages'][-1]['content']
  if method=='agentdrug':
   with tempfile.TemporaryDirectory() as folder:
    relay=FakeRelay(['invalid',correct]);candidate,detail=runner.agentdrug(case,relay,Path(folder))
    assert candidate==correct and len(relay.calls)==2
    assert all(x['cap']==256 for x in relay.calls)
    assert 'not chemically valid' in relay.calls[1]['messages'][0]['content']
  if method=='chatdrug':
   # Original parser still only selects first, not whichever output passes.
   with tempfile.TemporaryDirectory() as folder:
    relay=FakeRelay(['- CCCCCC\n- '+correct]*3)
    candidate,detail=runner.chatdrug(case,relay,Path(folder))
    assert not b.evaluate(case,candidate)['success']
 return True

if __name__=='__main__':
 report={'official_evaluator_cases':test_official(),'native_flow_tests':test_native()}
 dump(ROOT/'protocol_validation.json',report);print(json.dumps(report),flush=True)
