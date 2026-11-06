"""Precompute deterministic RDKit counts; no scoring/ranking changes."""
from pathlib import Path
import concurrent.futures,json
import pandas as pd
import benchmark as b
from transport import dump,sha
ROOT=Path(__file__).resolve().parent
SOURCE=Path('/data2/chenfuxin/pmo_submission_20260925/native_data')

def calculate(item):
 sm,keys=item
 return {k:b.mol_prop(sm,k) for k in keys}

def main():
 keys=sorted({key for case in b.cases() for key in b.constraints(case)})
 folder=ROOT/'reference';folder.mkdir(exist_ok=True)
 manifest={'keys':keys,'libraries':{}}
 for method,col in [('chatdrug','sequence'),('agentdrug','SMILES')]:
  src=SOURCE/(method+'_10000.csv');dst=folder/(method+'.json')
  db=pd.read_csv(src);smiles=[str(s).replace('\n','') for s in db[col]]
  assert len(smiles)==10000
  if not dst.exists():
   with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
    props=list(pool.map(calculate,[(s,keys) for s in smiles],chunksize=100))
   assert all(all(v is not None for v in p.values()) for p in props)
   dump(dst,[{'smiles':s,**p} for s,p in zip(smiles,props)])
  manifest['libraries'][method]={'source':str(src),'source_sha256':sha(src),'properties_sha256':sha(dst),'rows':len(smiles)}
  print('REFERENCE_READY',method,flush=True)
 dump(folder/'manifest.json',manifest)

if __name__=='__main__':main()
