"""Offline setup, all 23 oracle smoke checks, budget and AUC regression checks."""
import csv, importlib.metadata, json, pathlib, random, tempfile, warnings, subprocess, sys
import numpy as np
from pmo_common import ROOT, SEEDS, Ledger, BudgetExhausted, canonical, dump, sha, _auc, make_oracle
from task_specs import TASKS
warnings.filterwarnings('ignore')
BASE=pathlib.Path('/data2/chenfuxin/chatdrug_generalization_20260920')

def prepare():
    path=BASE/'data/ChatDrug_data/small_molecule/250k_rndm_zinc_drugs_clean_3.csv'
    # Ignore every provided property column. Only unscored SMILES enter sampling.
    with path.open() as f:pool=[r['smiles'].strip() for r in csv.DictReader(f)]
    initial={}
    for seed in SEEDS:
        order=list(range(len(pool)));random.Random(seed).shuffle(order);selected=[];seen=set()
        for i in order:
            sm=canonical(pool[i])
            if sm and sm not in seen:selected.append(sm);seen.add(sm)
            if len(selected)==100:break
        assert len(selected)==100;initial[str(seed)]=selected
    dump(ROOT/'prepared/initial.json',initial)
    dump(ROOT/'prepared/manifest.json',{'source':str(path),'sha256':sha(path),'rows':len(pool),'initial_size':100,'seeds':SEEDS,'property_columns_used':False})

def validate():
    from tdc import Oracle
    for row in json.loads((ROOT/'oracle/compat_manifest.json').read_text()):
        path=ROOT/'oracle'/(row['name']+'.pkl')
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    records={}
    for name,(oracle_name,_) in TASKS.items():
        # Match production: one objective per process; some upstream oracles share globals.
        script="from pmo_common import make_oracle; import json,sys; o=make_oracle(sys.argv[1]); print(json.dumps([float(o(s)) for s in ['CCO','c1ccccc1','CC(=O)Oc1ccccc1C(=O)O']]))"
        check=subprocess.run([sys.executable,'-c',script,oracle_name],cwd=ROOT,text=True,capture_output=True,check=True)
        values=json.loads(check.stdout.strip().splitlines()[-1])
        assert all(np.isfinite(x) and 0<=x<=1 for x in values),(name,values)
        records[name]={'oracle':oracle_name,'values':values};print(name,values,flush=True)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        p=pathlib.Path(tmp);seen=[]
        ledger=Ledger(p,lambda sm:seen.append(sm) or .5,2)
        ledger.score('CCO','test');ledger.score('OCC','duplicate');ledger.score('???','invalid');ledger.score('CCC','test')
        assert len(seen)==2 and len(ledger.buffer)==2
        try:ledger.score('CCCC','over_budget')
        except BudgetExhausted:pass
        else:raise AssertionError('Budget overspend')
        assert len(seen)==2
        resumed=Ledger(p,lambda sm:(_ for _ in ()).throw(AssertionError('cache failed')),2)
        assert resumed.score('OCC','resume')==.5
    # Constant 0.8 scores: the official trapezoidal origin is zero.
    buffer={str(i):[.8,i+1] for i in range(1000)}
    assert abs(_auc(buffer,10,True,100,1000)-.76)<1e-12
    assert abs(_auc(buffer,10,True,1,1000)-.7996)<1e-12
    versions={k:importlib.metadata.version(k) for k in ['PyTDC','rdkit','numpy','scikit-learn','pandas']}
    import tdc
    dependencies=[BASE/'upstream/ChatDrug/main_ChatDrug.py',BASE/'upstream/ChatDrug/utils.py',
        BASE/'upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py',
        pathlib.Path('/data2/chenfuxin/agentdrug_20260922/core_fixed.py'),
        pathlib.Path('/data2/chenfuxin/molingo_20260922/core_fixed.py'),
        pathlib.Path('/data2/chenfuxin/molingo_20260922/runner.py'),
        pathlib.Path('/data2/chenfuxin/molingo_20260922/upstream/toolset/tokenizer.py'),
        pathlib.Path('/data2/chenfuxin/molingo_20260922/upstream/toolset/drug_like_filtering.py'),
        pathlib.Path('/data2/chenfuxin/molingo_20260922/upstream/toolset/vocab20.json'),
        pathlib.Path(tdc.__file__).parent/'chem_utils/oracle/oracle.py',ROOT/'source/pmo/optimizer.py',
        ROOT/'oracle/drd2_current.pkl',ROOT/'oracle/gsk3b_current.pkl',ROOT/'oracle/jnk3_current.pkl',ROOT/'prepared/initial.json']
    dump(ROOT/'prepared/dependencies.json',{str(p):sha(p) for p in dependencies})
    dump(ROOT/'prepared/validation.json',{'passed':True,'oracles':records,'budget_checks':'canonical cache; invalid; strict cap; resume','auc_checks':'official function; 100 and 1 query sampling','versions':versions})

if __name__=='__main__':prepare();validate()
