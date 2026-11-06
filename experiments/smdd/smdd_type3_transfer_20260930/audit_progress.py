from pathlib import Path
from collections import Counter
import json,datetime
r=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')
print(datetime.datetime.now().isoformat())
for m in ['deepseek','chatdrug','agentdrug']:
 a=[json.loads(p.read_text()) for p in (r/'runs'/m).glob('*/result.json')]
 e=[json.loads(p.read_text()) for p in (r/'evaluation'/m).glob('*/result.json')]
 print(m,json.dumps({'generated':len(a),'generation_status':dict(Counter(x['status'] for x in a)),'evaluated':len(e),'evaluation_status':dict(Counter(x['status'] for x in e))}))
 for x in e:
  if x['status']=='errored':print(json.dumps(x))
p=r/'evaluation/chatdrug/smdd_003_5UEN_1'
for log in p.glob('queue/*/boltz.log'):print('BOLTZ',log.read_text(errors='replace')[-3500:])
