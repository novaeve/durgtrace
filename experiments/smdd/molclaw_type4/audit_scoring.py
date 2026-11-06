import os,sys,json
from pathlib import Path
import remote
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
host=sys.argv[1];c=manage.connect(host)
code='''from pathlib import Path
import json
'''
if host=='cpu':code+='''
r=Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929')
for m in ['chatdrug','agentdrug']:
 for p in sorted((r/m/'records').glob('*.json')):
  row=json.loads(p.read_text())
  if row['evaluation']!='errored':continue
  tid=p.stem;out=r/m/'run'/tid;ev=r/m/'evaluator'/tid
  print('TASK',m,tid,'AGENT',row.get('agent'),'SOLUTION',[(f.name,f.stat().st_size) for f in out.glob('*smi*')])
  print('RESULT',(ev/'result.json').read_text()[:2200])
  for q in (r/m/'eval_queue'/tid).glob('*/done.json'):
   d=json.loads(q.read_text())
   if 'error' in d:print('QUEUE_ERROR',str(q),d)
  for q in [ev/'container.log',r/m/'logs'/(tid+'.log')]:
   if q.exists():print('LOG',q.name,q.read_text(errors='replace')[-700:])
'''
else:code+='''
r=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3')
d=json.loads((r/'batch_status.json').read_text())
for tid,row in d['finished'].items():
 if row.get('evaluation_status') not in [None,'errored']:continue
 out=Path(row.get('reused_from',str(r/tid)))
 for _ in range(3):
  if out.exists():break
  choices=[p for p in r.parent.glob('*/'+tid) if p.is_dir()]
  if choices:out=choices[0]
 print('TASK',tid,json.dumps(row),'SOLUTION',[(str(f.relative_to(out)),f.stat().st_size) for f in out.glob('**/solution.smi')])
 print('LOCATION',str(out));print('FILES',[(p.name,p.stat().st_size) for p in out.iterdir() if p.is_file()] if out.exists() else [])
 for p in [out/'agent_result.json',out/'evaluation/result.json',out/'evaluator/result.json']:
  if p.exists():print('RESULT',p.name,p.read_text()[:2500])
 for p in out.glob('*.log'):
  print('LOG',p.name,p.read_text(errors='replace')[-1000:])
print('EVALUATION_SCRIPTS',[str(p) for p in (r/'source').glob('*eval*')])
'''
_,out,err=c.exec_command("python3 - <<'PY'\n"+code+"\nPY",timeout=120)
data=out.read().decode();errors=err.read().decode();rc=out.channel.recv_exit_status();c.close()
(remote.ROOT/f'scoring_audit_{host}.txt').write_text(data,encoding='utf-8')
print(data);print(errors);assert rc==0
