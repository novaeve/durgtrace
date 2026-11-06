import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
host=sys.argv[1];c=manage.connect(host)
if host=='cpu':
 code='''import pathlib,json,time,collections
r=pathlib.Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929')
for method in ['chatdrug','agentdrug']:
 rows=[json.loads(p.read_text()) for p in (r/method/'records').glob('*.json')]
 print('PROGRESS',method,json.dumps({'records':len(rows),'evaluation':dict(collections.Counter(x.get('evaluation') for x in rows)),'agent':dict(collections.Counter(x.get('agent') for x in rows)),'tool_error_tasks':sum(bool(x.get('tool_infrastructure_errors')) for x in rows)}))
 print('CURRENT',method,(r/method/'current.json').read_text())
 for w in json.loads((r/method/'current.json').read_text()).get('workers',[]):
  p=r/method/'logs'/(w['task']+'.log')
  print('WORKER_LOG',method,w['task'],p.read_text(errors='replace')[-550:] if p.exists() else 'missing')
print('PARALLEL',(r/'parallel_status.json').read_text())
print('STATUS_AGE_SECONDS',round(time.time()-(r/'parallel_status.json').stat().st_mtime))
'''
else:
 code='''import pathlib,json,time,collections,subprocess,pwd,os
r=pathlib.Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3')
d=json.loads((r/'batch_status.json').read_text());finished=d.pop('finished',[])
print('LIDDIA_STATUS',json.dumps(d));print('FINISHED_TYPE_COUNT',type(finished).__name__,len(finished))
for w in d.get('workers',{}).values():
 p=r/w['task']/'resource_wait.json'
 print('WORKER',w['task'],'PID_EXISTS',pathlib.Path('/proc',str(w['pid'])).exists(),'WAIT',p.read_text() if p.exists() else None)
items=list(finished.values()) if isinstance(finished,dict) else finished
print('FINISHED_SAMPLE',json.dumps(items[-2:]));print('FINISHED_COUNTS',collections.Counter(str(x.get('status',x.get('evaluation'))) for x in items if isinstance(x,dict)))
for pattern in ['*/resource_wait.json','*/oracles/*/resource_wait.json']:
 for p in r.glob(pattern):
  if p.stat().st_mtime>time.time()-600:print('WAIT',str(p.relative_to(r)),p.read_text()[:500])
print('GPU',subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total','--format=csv,noheader'],text=True))
procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader'],text=True)
for line in procs.splitlines():
 parts=[s.strip() for s in line.split(',')];p=pathlib.Path('/proc')/parts[1]
 try:
  user=pwd.getpwuid(p.stat().st_uid).pw_name;args=(p/'cmdline').read_bytes().decode(errors='replace').split(chr(0))
  label=[a for a in args if a.endswith('.py') or a in ['boltz.main','predict']]
  print('GPU_PROCESS',line,'USER',user,'PROGRAM',label[:3])
 except OSError:pass
print('DISK',subprocess.check_output(['df','-h','/data2/chenfuxin'],text=True))
jobs=pathlib.Path('/data2/chenfuxin/smdd_boltz_jobs')
for p in jobs.glob('*/resource_wait.json'):
 if p.stat().st_mtime>time.time()-300:print('POOL_WAIT',p.parent.name,p.read_text()[:500])
'''
manage.execute(c,code);c.close()
