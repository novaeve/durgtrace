"""GPU smoke using synthetic inputs, never a benchmark answer."""
from pathlib import Path
import json,time
from runtime import ROOT,gpu_run
job=ROOT/'preflight/boltz';job.mkdir(parents=True,exist_ok=True)
inp=job/'input.yaml'
inp.write_text('version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: ACDEFGHIKLMNPQRSTVWYACDEFGHIKLMNPQRSTVWY\n      msa: empty\n  - ligand:\n      id: B\n      smiles: CCO\nproperties:\n  - affinity:\n      binder: B\n')
started=time.time()
rc=gpu_run(inp,job/'out',job/'boltz.log',samples=1,seed=42,timeout=1200)
cifs=list((job/'out').rglob('*.cif'));aff=list((job/'out').rglob('affinity_*.json'))
result={'returncode':rc,'structures':len(cifs),'affinity_files':len(aff),'seconds':time.time()-started,'synthetic_input':True,'smoke_samples':1,'production_samples':10}
(ROOT/'preflight_boltz.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
assert rc==0 and cifs and aff
print('BOLTZ_PREFLIGHT_OK; model smoke still required',flush=True)
