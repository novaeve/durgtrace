"""Offline scoring only, original metric without modifications."""
from pathlib import Path
import json,argparse
from pharmacophore_3d import evaluate_3d_pharmacophore
ROOT=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('method');a=ap.parse_args()
rows=[]
for p in sorted((ROOT/'runs'/a.method).glob('*/result.json')):
    try:
        score=evaluate_3d_pharmacophore(str(p.parent/'solution.csv'),str(ROOT/'tasks'/p.parent.name/'ground_truth.json'))
    except Exception as e:score={'score':0,'n_correct':0,'n_required':3,'error':type(e).__name__}
    score.update(task=p.parent.name,passed=score['score']==1)
    (p.parent/'evaluation.json').write_text(json.dumps(score,indent=2));rows.append(score)
summary={'processed':len(rows),'expected':25,'correct_points':sum(r['n_correct'] for r in rows),'point_denominator':75,'passed_tasks':sum(r['passed'] for r in rows),'task_denominator':25,'rows':rows}
(ROOT/'runs'/a.method/'scores.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))
