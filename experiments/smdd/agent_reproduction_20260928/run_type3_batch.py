"""Frozen two-worker Type3 queue; no automatic replay of started tasks."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from runtime_safety import atomic_json,require_disk,ResourceUnavailable
from smdd_backends import INSTALL
from type3_support import TYPE3_ROOT

SOURCE=Path(__file__).resolve().parent
RUN='full_high_v1'
OUT=TYPE3_ROOT/'runs'/RUN
PYTHON=str(INSTALL/'envs/liddia/bin/python')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'batch.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=json.loads((TYPE3_ROOT/'manifest.json').read_text())
        for name,digest in manifest['source_hashes'].items():
            assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==digest,name
        assert not (OUT/'batch_status.json').exists(),'Restart requires explicit reconciliation'
        jobs=queue.Queue()
        for t in manifest['tasks']:jobs.put(t)
        guard=threading.Lock()
        state={'run':RUN,'pid':os.getpid(),'state':'running','total':52,'workers':{},'finished':{}}
        def save():
            state.update(updated=time.time(),completed=len(state['finished']),remaining=52-len(state['finished']))
            atomic_json(OUT/'batch_status.json',state)
        def update(gpu,**data):
            with guard:state['workers'][str(gpu)]=dict(gpu=gpu,**data);save()
        def worker(gpu):
            env=dict(os.environ,LIDDIA_FIXED_GPU=str(gpu),LIDDIA_POCKET_GPU=str(gpu),
                     PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
            while True:
                try:task=jobs.get_nowait()
                except queue.Empty:break
                out=OUT/task
                if out.exists():raise RuntimeError('Refusing to replay started task '+task)
                while True:
                    try:require_disk(OUT,50);break
                    except ResourceUnavailable as exc:update(gpu,task=task,phase='waiting_disk',error=str(exc));time.sleep(60)
                with (OUT/(task+'.launcher.log')).open('w') as log:
                    cmd=[PYTHON,'-u',str(SOURCE/'run_liddia_type3.py'),'--task',task,'--run',RUN,'--gpu',str(gpu)]
                    proc=subprocess.Popen(cmd,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT)
                    update(gpu,task=task,phase='agent',pid=proc.pid);ae=proc.wait()
                    result=json.loads((out/'agent_result.json').read_text()) if (out/'agent_result.json').exists() else {'status':'startup_failure'}
                    ee=None
                    if result['status'] in ('submitted','budget_exhausted','no_submission'):
                        proc=subprocess.Popen([PYTHON,'-u',str(SOURCE/'evaluate_liddia_type3.py'),task,str(out),'--gpu',str(gpu)],
                                              cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT)
                        update(gpu,task=task,phase='evaluation',pid=proc.pid);ee=proc.wait()
                    evaluation=json.loads((out/'evaluation/result.json').read_text()) if (out/'evaluation/result.json').exists() else {}
                record={'agent_exit':ae,'evaluation_exit':ee,'agent_status':result['status'],
                        'evaluation_status':evaluation.get('status'),'llm_calls':result.get('llm_calls'),
                        'tokens':result.get('tokens'),'budget_used':result.get('budget_used'),'time':time.time()}
                with guard:state['finished'][task]=record;save()
                print(task,json.dumps(record),flush=True)
                if result['status'] not in ('submitted','budget_exhausted','no_submission') or ee not in (None,0) or evaluation.get('status')=='errored':
                    update(gpu,task=task,phase='needs_attention',result=record)
                    # Keep other healthy worker progressing; no free task retries.
                    return
            update(gpu,phase='complete')
        with guard:save()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(worker,gpu) for gpu in (5,7)]
            for future in as_completed(futures):
                try:future.result()
                except Exception as exc:
                    with guard:state.setdefault('worker_errors',[]).append(repr(exc));save()
        with guard:
            state['state']='complete' if len(state['finished'])==52 and not any(v.get('phase')=='needs_attention' for v in state['workers'].values()) else 'needs_attention';save()

if __name__=='__main__':main()
