from pathlib import Path
import argparse,json,subprocess,time,yaml
from runtime import ROOT,ROOTFS,gpu_run,dump
p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('output');a=p.parse_args()
out=Path(a.output).resolve();results=out/'evaluation';results.mkdir(exist_ok=False);queue=results/'queue';queue.mkdir()
task=Path('/data/chenfuxin/a100_migration_20261016/workspace/yimin/zlc/molclaw_type4_20261003/tasks')/a.task
cmd=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind',str(ROOTFS),'/',
 '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/root','--ro-bind',str(task),'/eval/task',
 '--ro-bind',str(out),'/eval/output','--bind',str(results),'/eval/results','--bind',str(queue),'/queue',
 '--ro-bind',str(ROOT/'smdd_eval_bridge.py'),'/bridge.py','--chdir','/eval','--clearenv',
 '--setenv','PATH','/opt/conda/bin:/usr/bin:/bin','--setenv','LD_LIBRARY_PATH','/opt/conda/lib',
 '--setenv','HOME','/tmp','--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1',
 '--setenv','CUDA_VISIBLE_DEVICES','','/opt/conda/bin/python','/bridge.py']
with (results/'container.log').open('w') as log:
 proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
 try:
  while proc.poll() is None:
   for request in queue.glob('*/request.json'):
    done=request.parent/'done.json'
    if done.exists():continue
    data=json.loads(request.read_text());job=request.parent/'gpu';job.mkdir(exist_ok=True)
    yp=job/'input.yaml';yp.write_text(yaml.safe_dump(data['payload']))
    try:
     rc=gpu_run(yp,job/'out',job/'boltz.log',samples=data['samples'],seed=42)
     if rc:raise RuntimeError('GPU prediction exit '+str(rc))
     affinity=json.loads((job/'out/boltz_results_input/predictions/input/affinity_input.json').read_text())
     result={'affinity':affinity}
    except Exception as exc:result={'error':type(exc).__name__+': '+str(exc)}
    dump(done,result)
   time.sleep(1)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=20)
if not (results/'result.json').exists():raise RuntimeError('Evaluation produced no result')
print((results/'result.json').read_text())
