import sys
from pathlib import Path
import remote
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
if sys.argv[1]=='liddia':
 c=manage.connect('gpu')
 code="""from pathlib import Path
import json,collections
r=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3')
d=json.loads((r/'batch_status.json').read_text());rows=list(d['finished'].values())
print(json.dumps({'method':'LIDDIA','completed':len(rows),'counts':dict(collections.Counter(x.get('evaluation_status') for x in rows)),'workers':d.get('workers'),'state':d.get('state'),'updated':d.get('updated')}))
for tid,x in d['finished'].items():
 if x.get('evaluation_status') is None:print('MISSING_STATUS',tid,json.dumps(x))
"""
 manage.execute(c,code)
else:
 c=remote.connect()
 code="""from pathlib import Path
import json,collections
r=Path('/yimin/zlc/molclaw_type4_20261003')
rows=[json.loads(p.read_text()) for p in (r/'evaluation/molclaw').glob('*/result.json')]
print(json.dumps({'method':'MolClaw','completed':len(rows),'counts':dict(collections.Counter(x.get('status') for x in rows)),'queue':json.loads((r/'status.json').read_text())}))
"""
 remote.py(c,code)
c.close()
