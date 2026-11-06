"""Frozen zero-amplitude ChatDrug scorer, evaluated under original RDKit runtime."""
import ast, copy, json, pathlib, sys, os
ROOT = pathlib.Path(__file__).resolve().parent
BASE = pathlib.Path('/data2/chenfuxin/chatdrug_generalization_20260920')
sys.path.insert(0, str(BASE))
import pilot as p
from rdkit import rdBase, RDLogger
RDLogger.DisableLog('rdApp.*')
assert rdBase.rdkitVersion == '2022.09.4', rdBase.rdkitVersion
source = (BASE / 'full_experiment.py').read_text()
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'score')
ns = {'p':p}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(BASE/'full_experiment.py'),'exec'),ns)

def score(case,candidate):
    current=copy.deepcopy(case)
    current['thresholds']=[0 for _ in current['thresholds']]
    result=ns['score'](current,candidate)
    result.update(protocol='ChatDrug_zero_amplitude_Kekulize',rdkit_version=rdBase.rdkitVersion)
    return result

def dump(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)
