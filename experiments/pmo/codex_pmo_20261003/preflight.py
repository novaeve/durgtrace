from run import *
from oracle_server import OracleService
from guard import python_reason
from pmo_common import make_oracle
import tempfile
assert len(TASKS)==23
for path,digest in json.loads((LEGACY/'prepared/dependencies.json').read_text()).items():assert sha(path)==digest,path
with tempfile.TemporaryDirectory(dir=ROOT) as temp:
    out=Path(temp);service=OracleService(out,'qed',3,evaluator=lambda sm:0.3)
    result=service.score(['CC','invalid!','CC','CCC'])
    assert result['used']==3 and result['not_evaluated']==1
    assert [r['status'] for r in result['results']]==['new','invalid','duplicate']
    assert service.score(['CCC'])['used']==3
    ledger=service.ledger();auc,curve=complete_auc(ledger.rows,3);assert abs(auc-.25)<1e-10
    assert python_reason('from rdkit.Chem import QED; print(QED.qed(None))')
    assert python_reason('from rdkit import Chem; print(Chem.MolFromSmiles("CC"))') is None
    work=out/'workspace';work.mkdir();boundary=Boundary(out,work,'qed',3)
    result=boundary.python('from rdkit import Chem, rdBase\nfrom pathlib import Path\nassert not Path("/data2/chenfuxin/pmo_submission_20260925").exists()\nassert not Path("/data2/chenfuxin/molingo_20260922/private").exists()\nprint(rdBase.rdkitVersion)\nprint(Chem.MolToSmiles(Chem.MolFromSmiles("CC")))')
    assert result['exit_code']==0 and '2023.09.6' in result['output'],result
os.chdir(LEGACY);initial={}
for task in TASKS:
    path=SUBMISSION/'runs/deepseek'/task/'0/answers.jsonl'
    seed=json.loads(path.read_text().splitlines()[0]);assert seed['index']==1
    sm=canonical(seed['raw']);value=float(make_oracle(TASKS[task][0])(sm)) if sm else 0.0
    assert abs(value-seed['score'])<1e-10,(task,value,seed['score'])
    initial[task]={'raw':seed['raw'],'score':value,'source_sha256':sha(path)}
dump(ROOT/'preflight.json',{'passed':True,'tasks':23,'dependency_hashes_verified':True,'budget_duplicate_invalid_boundary_test':True,'auc_test':True,'isolated_rdkit':'2023.09.6','initial_answers_verified':initial})
print(json.dumps({'passed':True,'tasks':23,'initial_scores_match':True,'budget_and_isolation_verified':True}))
