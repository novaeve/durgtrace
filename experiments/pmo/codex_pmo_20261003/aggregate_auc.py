from pathlib import Path
import json,sys,math,hashlib,time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source_snapshot'))
from trajectory import complete_auc
rows=[]
for out in sorted((ROOT/'control/full').glob('*/0')):
    result=json.loads((out/'result.json').read_text())
    ledger_path=out/'oracle_queries.jsonl'
    ledger=[json.loads(x) for x in ledger_path.read_text().splitlines()]
    assert len(ledger)==result['oracle_submissions'] and 0<len(ledger)<=1000
    observed,curve=complete_auc(ledger,budget=len(ledger))
    auc=observed*len(ledger)/1000
    assert math.isclose(auc,result['auc_area_divided_by_budget'],abs_tol=1e-12)
    if len(ledger)==1000:assert math.isclose(auc,result['auc_top10'],abs_tol=1e-12)
    assert 0<=auc<=1
    rows.append({'target':out.parent.name,'status':result['status'],'submissions':len(ledger),'top10_auc_1k':auc,'top10_auc_observed':observed,'ledger_sha256':hashlib.sha256(ledger_path.read_bytes()).hexdigest()})
assert len(rows)==23
result={'method':'Codex (DeepSeek v4.1 Flash)','benchmark':'PMO-1K','target_count':23,'completed_1000':sum(r['submissions']==1000 for r in rows),'partial_targets_included':sum(r['submissions']<1000 for r in rows),'auc_protocol':'Trapezoidal area of actual recorded submission trajectory, start from zero, unique valid Top-10 mean, divide by 1000 for every target. No extrapolation or fill of unobserved tail.','sum_top10_auc':math.fsum(r['top10_auc_1k'] for r in rows),'mean_top10_auc':math.fsum(r['top10_auc_1k'] for r in rows)/23,'time':time.time(),'targets':rows}
p=ROOT/'pmo_1k_all23_auc_20261004.json';p.write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='targets'},ensure_ascii=False))
print(json.dumps(rows,ensure_ascii=False))
