"""Real high-thinking/Pocket2Mol/evaluator smoke; no formal task results reused."""
import json
import os
from pathlib import Path
import tempfile
import sys
from rdkit import Chem
from runtime_safety import atomic_json
from smdd_backends import INSTALL
from smdd_liddia_tools import Pocket2MolTool,GraphGATool,BudgetGate
from type3_support import BASE,TYPE3_ROOT,Agent,prepare,scaffold_mcs_fraction
from evaluate_liddia_type3 import evaluate

root=TYPE3_ROOT/'smoke';root.mkdir(exist_ok=False)
os.environ.update(LIDDIA_FIXED_GPU='7',LIDDIA_POCKET_GPU='7',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
manifest=json.loads((TYPE3_ROOT/'manifest.json').read_text())
checks={}
with tempfile.TemporaryDirectory() as tmp:
    for task in manifest['tasks']:
        prepare(BASE/'tasks'/task,Path(tmp)/task)
checks['public_inputs']=52
task=manifest['tasks'][0]
derived=prepare(BASE/'tasks'/task,root/'public')
agent=Agent(root);answer=agent.ask('Compute 17 * 19. Give only the integer.','transport_smoke')
record=json.loads((root/'api/001.json').read_text());request=record['request']
assert request['model']=='deepseek-v4.1-flash' and request['enable_thinking'] is True and request['reasoning_effort']=='high'
assert request['temperature']==1 and 'max_tokens' not in request and 'seed' not in request
assert '323' in answer,answer
checks['transport']={'model':request['model'],'reasoning_effort':request['reasoning_effort'],
                     'usage':record['response'].get('usage'),'finish_reason':record['response']['choices'][0]['finish_reason']}
sys.path.insert(0,str(BASE/'upstream'))
from metrics.scaffold import assess_scaffold_mcs
reference=Chem.MolFromSmiles(derived['reference_smiles'])
for i,smi in enumerate([derived['reference_smiles'],'c1ccccc1','C1CCCCC1']):
    path=root/f'candidate_{i}.smi';path.write_text(smi+'\n')
    local=scaffold_mcs_fraction(reference,Chem.MolFromSmiles(smi))
    official=assess_scaffold_mcs(str(path),str(root/'public/reference.sdf'))
    assert abs(local-official)<1e-12,(local,official)
checks['scaffold_matches_official']=3
pocket=Pocket2MolTool(INSTALL,root/'generation',derived['center'],seed=42,beam_size=1,device='cuda',gpu=7)
df,meta=pocket(root/'public/protein.pdb',1)
assert len(df)==1,'Pocket2Mol smoke produced no valid molecule'
checks['pocket']=meta
ga=GraphGATool(seed=42)
optimized,ga_meta=ga(df,'QED',1,root/'optimization',score_cap=5)
assert len(optimized)>0,'GraphGA smoke returned no molecule'
checks['graphga']=ga_meta
# Explicitly verify a failed oracle attempt still spends one shared budget unit.
gate=BudgetGate(root/'diagnostic_budget.jsonl',{'boltz':lambda s:(_ for _ in ()).throw(RuntimeError('intentional_test_failure')),'admet':lambda s:{}})
try:gate.predict('boltz','CC')
except RuntimeError:pass
assert gate.used['boltz']==1
checks['failed_oracle_charged']=True
(root/'solution.smi').write_text(df.iloc[0]['SMILES']+'\n')
atomic_json(root/'preflight_checks.json',checks)
result=evaluate(task,root,7)
assert result['status'] in ('passed','failed'),result
steps=result.get('steps',[])
assert len(steps)==5,steps
assert not any(s.get('status')=='errored' for s in steps),steps
checks['official_evaluation']={'status':result['status'],'step_names':[s.get('name') for s in steps]}
atomic_json(root/'preflight_checks.json',checks)
atomic_json(root/'verification.json',{'status':'passed','checks':checks,'formal_results_reused':False})
print(json.dumps({'status':'passed','task':task,'checks':list(checks)}),flush=True)
