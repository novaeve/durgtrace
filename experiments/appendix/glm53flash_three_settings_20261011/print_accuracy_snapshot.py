import collections,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
r=json.loads((Path(__file__).resolve().parent/'latest_report.json').read_text())
print('AS_OF '+datetime.fromtimestamp(r['updated'],timezone(timedelta(hours=8))).isoformat())
order=['ChatDrug','AgentDrug','MolLingo','MolClaw','SoL-Pi','Codex','GLM_direct']
for method in order:
 m=r['methods'][method];groups=m['groups'];success=sum(g['success'] for g in groups)
 statuses=collections.Counter()
 for g in groups:statuses.update(g['statuses'])
 print(json.dumps({'method':method,'processed':m['processed'],'correct':success,
  'accuracy':round(100*success/m['processed'],2),'phase':m['state']['phase'],
  'statuses':dict(statuses),'error':m['state'].get('error')},ensure_ascii=False))
 cells=[]
 for s in ['1_original_chatdrug','2_s2_prompt_chatdrug','3_original_s2']:
  for prop in ['LogP','QED']:
   g=next(g for g in groups if g['setting']==s and g['property']==prop)
   cells.append(f"{g['success']}/{g['processed']} ({100*g['success']/g['processed']:.2f}%)" if g['processed'] else '0/0')
 print('| '+method+' | '+' | '.join(cells)+' |')
