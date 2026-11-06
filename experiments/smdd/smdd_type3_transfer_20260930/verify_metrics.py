from pathlib import Path
import json
from runtime import ROOT,UPSTREAM,isolated,dump
w=ROOT/'smoke/metrics';w.mkdir(parents=True,exist_ok=True)
script="""import sys,json
sys.path.insert(0,'/eval/code')
from metrics.boltz_manager import BoltzManager
from metrics.interaction import build_consensus_fingerprint
from rdkit import Chem
from metrics.scaffold import assess_scaffold_mcs,assess_tanimoto_similarity
m=next(x for x in Chem.SDMolSupplier('/eval/ref/reference.sdf') if x is not None)
open('solution.smi','w').write(Chem.MolToSmiles(m))
assert abs(assess_tanimoto_similarity('solution.smi','/eval/ref/reference.sdf')-1)<1e-6
assert abs(assess_scaffold_mcs('solution.smi','/eval/ref/reference.sdf')-1)<1e-6
b=BoltzManager();c=b.extract_all_complexes_from_results('/eval/ref/gt_results/boltz_results_gt_dock','gt_dock')
assert len(c)==10,len(c)
f=build_consensus_fingerprint([(x['lig_pdb'],x['prot_pdb']) for x in c],0.6)
assert f,'empty reference fingerprint'
print(json.dumps({'reference_structures':len(c),'reference_consensus_interactions':len(f),'self_similarity_checks':'passed'}))
"""
(w/'check.py').write_text(script)
out,rc=isolated(['python','/workspace/check.py'],w,180,binds=['--ro-bind',str(UPSTREAM),'/eval/code','--ro-bind',str(ROOT/'tasks/smdd_003_1JVP_1'),'/eval/ref'])
(w/'log.txt').write_text(out);print(out[-2000:]);assert rc==0
assert 'PLIP Analysis Error' not in out
print('Official metric preflight passed')

