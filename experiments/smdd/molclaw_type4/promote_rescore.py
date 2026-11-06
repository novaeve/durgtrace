import os,sys,json,hashlib,shlex
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
gpu=manage.connect('gpu');cpu=manage.connect('cpu');g=gpu.open_sftp();s=cpu.open_sftp()
root='/data2/chenfuxin/smdd_rescore_20261004';manifest=json.loads(g.open(root+'/manifest.json').read())['tasks']
assert json.loads(g.open(root+'/complete.json').read())['count']==8
updates=[]
for item in manifest:
 target=g if item['method']=='liddia' else s
 old=g.open(item['output']+'/original_result.json','rb').read()
 new=g.open(item['output']+'/evaluation/result.json','rb').read();score=json.loads(new);assert score['status'] in ['passed','failed']
 current=target.open(item['original_result'],'rb').read()
 if current!=old:
  if json.loads(current)==score:continue
  raise RuntimeError('Concurrent scoring modification: '+item['task'])
 solution=target.open(item['original_output']+'/solution.smi','rb').read();assert hashlib.sha256(solution).hexdigest()==item['solution_sha256']
 backup=item['original_result']+'.before_rescore_20261004'
 try:target.stat(backup)
 except FileNotFoundError:
  with target.open(backup,'wb') as f:f.write(old)
 tmp=item['original_result']+'.rescore_tmp'
 with target.open(tmp,'wb') as f:f.write(new)
 target.posix_rename(tmp,item['original_result'])
 updates.append(dict(item,status=score['status']))
def remote(c,code):
 _,o,e=c.exec_command('python3 -c '+shlex.quote(code));out=o.read().decode();err=e.read().decode();assert o.channel.recv_exit_status()==0,err;print(out)
cpu_updates=[d for d in updates if d['method']!='liddia']
remote(cpu,"""from pathlib import Path
import json,sys,collections
r=Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929');sys.path.insert(0,str(r));import batch
for d in UPDATES:
 p=r/d['method']/'records'/(d['task']+'.json');old=json.loads(p.read_text());assert old['evaluation']=='errored'
 backup=p.with_suffix('.json.before_rescore_20261004');backup.write_text(p.read_text())
 old['evaluation']=d['status'];old['rescoring']={'date':'20261004','original_submission_sha256':d['solution_sha256'],'gpu_output':d['output']};batch.dump(p,old)
ids=(r/'tasks340.txt').read_text().splitlines()
for method in ['chatdrug','agentdrug']:
 report=batch.summary(r/method,ids);print(method,json.dumps(report))
 if report['completed']==340:
  (r/method/'experiment.exit').write_text('0' if not report['infrastructure_errors'] else '2')
  (r/method/'RESULTS.md').write_text(f"{method}: 340/340 terminal tasks; {report['passed']}/340 passed; {report['infrastructure_errors']} infrastructure errors.\\n")
""".replace('UPDATES',repr(cpu_updates)))
remote(gpu,"""from pathlib import Path
import json,collections
r=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3');p=r/'batch_status.json';state=json.loads(p.read_text())
backup=r/'batch_status.before_rescore_20261004.json'
if not backup.exists():backup.write_text(p.read_text())
for d in UPDATES:
 state['finished'][d['task']]['evaluation_status']=d['status'];state['finished'][d['task']]['rescoring']={'date':'20261004','gpu_output':d['output']}
tmp=p.with_suffix('.rescore_tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(p)
print('liddia',dict(collections.Counter(d.get('evaluation_status') for d in state['finished'].values())))
""".replace('UPDATES',repr([d for d in updates if d['method']=='liddia'])))
print('PROMOTED',len(updates),'original submissions unchanged; archived previous evaluations')
g.close();s.close();gpu.close();cpu.close()
