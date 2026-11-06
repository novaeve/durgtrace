from pathlib import Path
import sys,json,math,time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source_snapshot'))
from trajectory import complete_auc
rows=[]
for out in sorted((ROOT/'control/full').glob('*/0')):
    r=json.loads((out/'result.json').read_text());ledger=[json.loads(l) for l in (out/'oracle_queries.jsonl').read_text().splitlines()]
    n=len(ledger);assert n==r['oracle_submissions'] and 0<n<=1000
    observed,curve=complete_auc(ledger,budget=n)
    area=observed*n;last=curve[-1]['top10_mean'];filled=(area+(1000-n)*last)/1000
    assert 0<=filled<=1
    rows.append({'target':out.parent.name,'status':r['status'],'submissions':n,'last_top10_mean':last,'auc_without_tail':area/1000,'auc_with_constant_tail':filled})
assert len(rows)==23
report={'method':'Codex (DeepSeek v4.1 Flash)','benchmark':'PMO-1K','targets':rows,'tail_fill_policy':'All stopped targets included as final reports; retain actual submission positions and initial-zero trapezoidal integration; extend final Top-10 mean as constant to submission 1000; no extra oracle calls or manufactured molecules.','sum_top10_auc':math.fsum(x['auc_with_constant_tail'] for x in rows),'mean_top10_auc':math.fsum(x['auc_with_constant_tail'] for x in rows)/23,'target_count':23,'time':time.time()}
(ROOT/'pmo_1k_all23_auc_tailfilled_20261004.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='targets'}))
print(json.dumps([r for r in rows if r['submissions']<1000]))
