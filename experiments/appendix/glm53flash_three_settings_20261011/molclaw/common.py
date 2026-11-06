import ast
import functools
import json
from pathlib import Path
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/data2/chenfuxin/chatdrug_generalization_20260920/upstream/S2-TOMG-Bench/utils/evaluation.py')
RDLogger.DisableLog('rdApp.*')
node=next(n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='mol_prop')
ns={'Chem':Chem,'Descriptors':Descriptors}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),ns)
mol_prop=functools.lru_cache(maxsize=30000)(ns['mol_prop'])

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    tmp.replace(path)

def cases():
    return json.loads((ROOT/'cases.json').read_text())

def score(case,candidate):
    descriptor='logP' if case['property']=='LogP' else 'qed'
    direction=case['objectives'][0][1]
    valid=isinstance(candidate,str) and bool(mol_prop(candidate,'validity'))
    before=mol_prop(case['smiles'],descriptor)
    after=mol_prop(candidate,descriptor) if valid else None
    success=bool(valid and (after<before if direction==-1 else after>before))
    return dict(success=success,valid=bool(valid),candidate=candidate,input_property=before,
                output_property=after,direction=direction,protocol='S2',kekulize=False,amplitude=0)
