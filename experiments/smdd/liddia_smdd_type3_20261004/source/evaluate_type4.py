from pathlib import Path
import argparse
import json
import subprocess
import time
from smdd_backends import ROOT, boltz_payload

p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('output');p.add_argument('--gpu',type=int,default=1);a=p.parse_args()
out=Path(a.output).resolve();results=out/'evaluation';results.mkdir(exist_ok=False)
queue=results/'queue';queue.mkdir()
cmd=['bwrap','--unshare-all','--die-with-parent','--new-session',
 '--ro-bind',str(ROOT/'evaluator_rootfs'),'/', '--proc','/proc','--dev','/dev',
 '--tmpfs','/tmp','--tmpfs','/root','--ro-bind',str(ROOT/'benchmark/tasks'/a.task),'/eval/task',
 '--ro-bind',str(out),'/eval/output','--bind',str(results),'/eval/results',
 '--bind',str(queue),'/queue','--ro-bind',str(Path(__file__).with_name('smdd_eval_bridge.py')),'/bridge.py',
 '--chdir','/eval','--clearenv','--setenv','PATH','/opt/conda/bin:/usr/bin:/bin',
 '--setenv','LD_LIBRARY_PATH','/opt/conda/lib','--setenv','HOME','/tmp',
 '--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1',
 '--setenv','CUDA_VISIBLE_DEVICES','','/opt/conda/bin/python','/bridge.py']
with (results/'container.log').open('w') as log:
    proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
    try:
        while proc.poll() is None:
            for request in queue.glob('*/request.json'):
                done=request.parent/'done.json'
                if done.exists():continue
                data=json.loads(request.read_text())
                try:
                    result={'affinity':boltz_payload(data['payload'],request.parent/'gpu',gpu=a.gpu,samples=data['samples'])}
                except Exception as exc:
                    result={'error':type(exc).__name__+': '+str(exc)}
                tmp=done.with_suffix('.tmp');tmp.write_text(json.dumps(result));tmp.replace(done)
            time.sleep(1)
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=20)
if not (results/'result.json').exists():
    raise RuntimeError('Evaluation did not produce a result; inspect '+str(results/'container.log'))
print((results/'result.json').read_text())
