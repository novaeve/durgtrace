import os,sys,json,hashlib,shlex
import remote
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
DEST='/data2/chenfuxin/smdd_rescore_20261004'
CPU=manage.CPU
LID='/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3'
tasks={'chatdrug':['smdd_004_ABL1_6','smdd_004_CYP1B1_0','smdd_004_CYP1B1_17'],'agentdrug':['smdd_004_DHFR_22','smdd_004_DHODH_14'],'liddia':['smdd_004_ABL1_11','smdd_004_ACE_6','smdd_004_CA2_17']}
cpu=manage.connect('cpu');gpu=manage.connect('gpu');cs=cpu.open_sftp();gs=gpu.open_sftp()
metrics=['/eval/eval_entrypoint.py','/eval/code/metrics/lead_optimization.py','/eval/code/metrics/boltz_manager.py']
def command(c,cmd):
 _,o,e=c.exec_command(cmd,timeout=90);result=o.read().decode();error=e.read().decode();assert o.channel.recv_exit_status()==0,error;return result
cpu_hash=command(cpu,'docker run --rm --network none --entrypoint sha256sum smdd-evals:359ef1d7 '+' '.join(metrics))
gpu_hash=command(gpu,'sha256sum '+' '.join('/data2/chenfuxin/liddia_smdd_type4_20260928/evaluator_rootfs'+p for p in metrics))
assert [l.split()[0] for l in cpu_hash.splitlines()]==[l.split()[0] for l in gpu_hash.splitlines()], 'Evaluator code differs'
command(gpu,'mkdir -p '+DEST+'/source '+DEST+'/jobs')
state=json.loads(gs.open(LID+'/batch_status.json').read());manifest=[]
for method,ids in tasks.items():
 for tid in ids:
  if method=='liddia':
   out=state['finished'][tid].get('reused_from',LID+'/'+tid);s=gs;resultpath=out+'/evaluation/result.json'
  else:out=CPU+'/'+method+'/run/'+tid;s=cs;resultpath=CPU+'/'+method+'/evaluator/'+tid+'/result.json'
  solution=s.open(out+'/solution.smi','rb').read();old=s.open(resultpath,'rb').read()
  assert json.loads(old)['status']=='errored' and solution.strip()
  dest=DEST+'/jobs/'+method+'/'+tid;command(gpu,'mkdir -p '+shlex.quote(dest))
  for name,data in [('solution.smi',solution),('original_result.json',old)]:
   with gs.open(dest+'/'+name,'wb') as f:f.write(data)
  manifest.append({'method':method,'task':tid,'original_output':out,'original_result':resultpath,'output':dest,'solution_sha256':hashlib.sha256(solution).hexdigest()})
src=LID+'/source'
for name in ['evaluate_type4.py','smdd_eval_bridge.py','smdd_backends.py','runtime_safety.py']:
 data=gs.open(src+'/'+name,'rb').read()
 if name=='smdd_eval_bridge.py':data=data.replace(b'range(1900)',b'range(21600)')
 with gs.open(DEST+'/source/'+name,'wb') as f:f.write(data)
with gs.open(DEST+'/manifest.json','w') as f:f.write(json.dumps({'tasks':manifest,'evaluator_hashes':cpu_hash,'scope':'score original submissions only; samples=10, seed=42; queue wait extended to six hours'},indent=2))
(remote.ROOT/'rescore_manifest.json').write_text(json.dumps(manifest,indent=2))
print('STAGED',len(manifest),'unchanged submissions; official evaluator hashes match')
print(command(gpu,'nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader'))
cs.close();gs.close();cpu.close();gpu.close()
