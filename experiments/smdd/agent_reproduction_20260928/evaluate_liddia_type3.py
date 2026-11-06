"""Original Type3 evaluator; transport full Boltz predictions including CIF."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from smdd_backends import ROOT as TYPE4_ROOT, boltz_payload
from runtime_safety import atomic_json
from type3_support import BASE,TYPE3_ROOT

def evaluate(task,out,gpu):
    out=Path(out).resolve();results=out/'evaluation';results.mkdir(exist_ok=False)
    if not (out/'solution.smi').exists() or not (out/'solution.smi').read_text().strip():
        result={'task_id':task,'status':'failed','reason':'missing_or_empty_submission','steps':[]}
        atomic_json(results/'result.json',result);return result
    queue=results/'queue';queue.mkdir()
    cmd=['bwrap','--unshare-all','--die-with-parent','--new-session',
         '--ro-bind',str(TYPE4_ROOT/'evaluator_rootfs'),'/', '--proc','/proc','--dev','/dev',
         '--tmpfs','/tmp','--tmpfs','/root','--tmpfs','/eval','--tmpfs','/work',
         '--ro-bind',str(BASE/'tasks'/task),'/eval/task','--ro-bind',str(out),'/eval/output',
         '--bind',str(results),'/eval/results','--ro-bind',str(BASE/'upstream'),'/eval/code',
         '--bind',str(queue),'/queue','--ro-bind',str(Path(__file__).with_name('type3_eval_bridge.py')),'/bridge.py',
         '--chdir','/eval','--clearenv','--setenv','PATH','/opt/conda/bin:/usr/bin:/bin',
         '--setenv','LD_LIBRARY_PATH','/opt/conda/lib','--setenv','HOME','/tmp',
         '--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1','--setenv','MKL_NUM_THREADS','1',
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
                        import yaml
                        payload=yaml.safe_load((request.parent/data['yaml_name']).read_text())
                        value=boltz_payload(payload,request.parent/'gpu',gpu=gpu,samples=data['samples'],job_name=Path(data['yaml_name']).stem)
                        predicted=Path(value['prediction_directory'])
                        # /queue is shared with the official evaluator, preserve exact tree.
                        # Absolute host symlinks are inaccessible inside bwrap: use relative path.
                        (request.parent/'out').symlink_to(os.path.relpath(predicted,request.parent),target_is_directory=True)
                        result={'returncode':0,'structures':len(list(predicted.rglob('*.cif')))}
                    except Exception as exc:result={'error':type(exc).__name__+': '+str(exc)}
                    atomic_json(done,result)
                time.sleep(1)
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=20)
    path=results/'result.json'
    if not path.exists():raise RuntimeError('Official evaluator produced no result: '+str(results/'container.log'))
    result=json.loads(path.read_text())
    if result['status']=='errored' and any(s.get('name')=='Validity' and s.get('status')=='failed' for s in result.get('steps',[])):
        atomic_json(results/'raw_result.json',result)
        result['status']='failed';result['adjudication']={'reason':'Invalid molecule counts as failed; same protocol as Codex/MolClaw','raw_result':'raw_result.json'}
        atomic_json(path,result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('output');p.add_argument('--gpu',type=int,required=True);a=p.parse_args()
    print(json.dumps(evaluate(a.task,a.output,a.gpu)))
