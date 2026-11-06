"""Type3 public input handling and the existing common high-thinking transport."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
import yaml
from rdkit import Chem
from rdkit.Chem import rdFMCS
from rdkit.Chem.Scaffolds import MurckoScaffold
from runtime_safety import atomic_json
from smdd_liddia_tools import BudgetExhausted
from prepare_type4 import prepare as prepare_structures

BASE=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')
TYPE3_ROOT=Path('/data2/chenfuxin/liddia_smdd_type3_20261004')
sys.path.insert(0,str(BASE))
from runtime import API
from agent_harness.obfuscate import obfuscate_task

def prepare(task_dir,output):
    task_dir=Path(task_dir)
    task=yaml.safe_load((task_dir/'task.yaml').read_text())
    assert set(task['input_files'])=={'complex.pdb','reference.sdf'}
    public=Path(obfuscate_task(str(task_dir),'task_public'))
    try:
        assert {p.name for p in public.iterdir()}=={'complex.pdb','reference.sdf'}
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp)
            for name in task['input_files']:shutil.copyfile(public/name,stage/name)
            limited={k:task[k] for k in ('description','target_ligand','pocket_residues','input_files')}
            limited['id']='task_public'
            (stage/'task.yaml').write_text(yaml.safe_dump(limited))
            return prepare_structures(stage,output)
    finally:
        shutil.rmtree(public)

class Agent:
    def __init__(self,out):
        self.api=API(out);self.calls=[];self.out=out;self.tokens=0
    def ask(self,prompt,label,system='You are a chemist expert'):
        if len(self.calls)>=100 or self.tokens>=10_000_000:
            raise BudgetExhausted('llm')
        messages=[{'role':'system','content':system},{'role':'user','content':prompt}]
        call={'label':label,'messages':messages};self.calls.append(call)
        atomic_json(self.out/'llm_calls.json',self.calls)
        response=self.api.complete(messages,temperature=1)
        choice=response['choices'][0];usage=response.get('usage',{})
        call.update(output=choice['message'].get('content'),reasoning_content=choice['message'].get('reasoning_content'),
                    finish_reason=choice.get('finish_reason'),usage=usage,model=response.get('model'))
        self.tokens+=usage.get('total_tokens',0)
        atomic_json(self.out/'llm_calls.json',self.calls)
        if choice.get('finish_reason')=='length':raise RuntimeError('LLM output truncated; original response preserved')
        if not isinstance(call['output'],str):raise RuntimeError('LLM returned no textual response')
        return call['output']

def scaffold_mcs_fraction(reference,mol):
    """Same scaffold MCS definition/defaults/timeout as official metrics.scaffold."""
    try:
        a=MurckoScaffold.GetScaffoldForMol(reference);b=MurckoScaffold.GetScaffoldForMol(mol)
        denom=max(a.GetNumHeavyAtoms(),b.GetNumHeavyAtoms())
        if denom==0:return 1.0
        mcs=rdFMCS.FindMCS([a,b],timeout=10)
        common=Chem.MolFromSmarts(mcs.smartsString)
        return (common.GetNumAtoms() if common else 0)/denom
    except Exception:return 1.0
