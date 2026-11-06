from pathlib import Path
import json
import tempfile
from smdd_liddia_tools import Pocket2MolTool
from smdd_backends import ROOT,INSTALL

public=ROOT/'runs/pilot_flowfix1/smdd_004_ABL1_1/public'
derived=json.loads((public/'derived.json').read_text())
out=ROOT/'runs/runtimefix_preflight'
out.mkdir(exist_ok=True)
tool=Pocket2MolTool(INSTALL,out,derived['center'],seed=42,beam_size=1,device='cuda',gpu=3)
df,meta=tool(public/'protein.pdb',1)
assert len(df)>=1
assert not list(Path(meta['job']).rglob('samples_*.pt'))
(out/'pocket_result.json').write_text(json.dumps({'smiles':list(df.SMILES),'metadata':meta,'snapshots':0},indent=2))
print(json.dumps({'valid_molecules':len(df),'snapshots':0,'job':meta['job']}))
