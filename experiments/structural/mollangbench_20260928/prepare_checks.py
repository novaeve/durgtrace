"""Compile public checks and cache native library descriptors without gold data."""
from pathlib import Path
import concurrent.futures,json,collections
import pandas as pd
import public_checks as checks
from transport import dump,sha
ROOT=Path(__file__).resolve().parent
LIB=Path('/data2/chenfuxin/pmo_submission_20260925/native_data')
def compute(s):return {'smiles':s,'props':checks.descriptors(s)}
def main():
 cases=json.loads((ROOT/'data/cases.json').read_text());plans={c['id']:checks.compile_case(c) for c in cases}
 folder=ROOT/'checks';folder.mkdir(exist_ok=True);dump(folder/'plans.json',plans)
 coverage={}
 for c in cases:
  p=plans[c['id']];g=coverage.setdefault(c['task'],collections.Counter());g['cases']+=1;g['with_checks']+=bool(p['rules']);g['complete_verifier']+=p['complete_task_verifier'];g['rules']+=len(p['rules'])
 manifest={'checks_code_sha256':sha(ROOT/'public_checks.py'),'public_cases_sha256':sha(ROOT/'data/cases.json'),'plans_sha256':sha(folder/'plans.json'),'coverage':coverage,'libraries':{}}
 for method,col in [('chatdrug','sequence'),('agentdrug','SMILES')]:
  src=LIB/(method+'_10000.csv');dst=folder/(method+'_library.json')
  smiles=[str(x).replace('\n','') for x in pd.read_csv(src)[col]];assert len(smiles)==10000
  with concurrent.futures.ProcessPoolExecutor(4) as pool:rows=list(pool.map(compute,smiles,chunksize=100))
  assert all(r['props']['valid'] for r in rows)
  dump(dst,rows);manifest['libraries'][method]={'source':str(src),'source_sha256':sha(src),'descriptor_sha256':sha(dst),'size':len(rows)}
  print('PREPARED',method,flush=True)
 dump(folder/'manifest.json',manifest);print(json.dumps(coverage),flush=True)
if __name__=='__main__':main()
