"""Three disjoint task workers; adopt the existing in-flight task without replay."""
import concurrent.futures
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
from runtime_safety import atomic_json, require_disk, ResourceUnavailable
from smdd_backends import ROOT, INSTALL

RUN = 'full_type4_parallel3'
OUT = ROOT/'runs'/RUN
SOURCE = OUT/'source'
PYTHON = str(INSTALL/'envs/liddia/bin/python')

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def read(path):
    return json.loads(path.read_text()) if path.exists() else {}

def alive(pid):
    p=Path('/proc')/str(pid)/'stat'
    return p.exists() and p.read_text().split(') ')[1][0] != 'Z'

def main():
    with (OUT/'batch.lock').open('w') as batch_lock:
        fcntl.flock(batch_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=read(OUT/'manifest.json')
        for name,digest in manifest['source_hashes'].items():
            assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==digest, name
        assert not (OUT/'batch_status.json').exists(), 'Restart requires explicit reconciliation; never replay started tasks'
        adoption=manifest['adoption']
        state={'run':RUN,'pid':os.getpid(),'state':'running','total':340,
               'concurrency':3,'workers':{},'finished':manifest['inherited']}
        guard=threading.Lock()
        jobs=queue.Queue()
        for task in manifest['pending']: jobs.put(task)
        def save():
            state.update(updated=now(),completed=len(state['finished']),remaining=340-len(state['finished']))
            atomic_json(OUT/'batch_status.json',state)
        def worker_state(gpu,**kwargs):
            with guard:
                state['workers'][str(gpu)]=dict(gpu=gpu,**kwargs);save()
        def launch(cmd,env,log,gpu,task,phase):
            proc=subprocess.Popen(cmd,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT)
            worker_state(gpu,task=task,phase=phase,pid=proc.pid)
            return proc.wait()
        def finish(task,path,ae,ee,adopted=False):
            agent=read(path/'agent_result.json'); evaluation=read(path/'evaluation/result.json')
            record={'agent_exit':ae,'evaluation_exit':ee,'agent_status':agent.get('status','startup_failure'),
                    'evaluation_status':evaluation.get('status'),'budget_used':agent.get('budget_used'),
                    'mode':'adopted_inflight' if adopted else 'agent_and_evaluation','time':now()}
            if adopted: record['reused_from']=str(path)
            with guard:
                assert task not in state['finished']
                state['finished'][task]=record;save()
            print(now(),task,'END',json.dumps(record),flush=True)
        def worker(gpu,adopt=False):
            env=dict(os.environ,LIDDIA_FIXED_GPU=str(gpu),LIDDIA_POCKET_GPU=str(gpu),
                     OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
            if adopt:
                task=adoption['task']; path=Path(adoption['output'])
                worker_state(gpu,task=task,phase='adopting_'+adoption['phase'],pid=adoption['child_pid'])
                while alive(adoption['child_pid']): time.sleep(10)
                ee=None
                if adoption['phase']=='agent' and (path/'solution.smi').exists():
                    with (OUT/(task+'.adoption.log')).open('a') as log:
                        ee=launch([PYTHON,'-u',str(SOURCE/'evaluate_type4.py'),task,str(path),'--gpu',str(gpu)],env,log,gpu,task,'evaluation')
                finish(task,path,None,ee,True)
                # Old dispatcher is stopped, so it cannot advance to another task.
                if alive(adoption['parent_pid']):
                    os.kill(adoption['parent_pid'],signal.SIGTERM)
                    os.kill(adoption['parent_pid'],signal.SIGCONT)
                old=Path(adoption['parent_run'])/'batch_status.json'
                previous=read(old);previous.update(state='handed_off',successor=RUN,updated=now())
                atomic_json(old,previous)
            while True:
                try: task=jobs.get_nowait()
                except queue.Empty: break
                worker_state(gpu,task=task,phase='preflight')
                while True:
                    try: require_disk(OUT,minimum_gib=50);break
                    except ResourceUnavailable as exc:
                        worker_state(gpu,task=task,phase='waiting_disk',error=str(exc));time.sleep(60)
                path=OUT/task
                assert not path.exists(), 'Refusing duplicate task '+task
                with (OUT/(task+'.launcher.log')).open('w') as log:
                    ae=launch([PYTHON,'-u',str(SOURCE/'run_liddia_type4.py'),'--task',task,'--run',RUN,'--gpu',str(gpu)],env,log,gpu,task,'agent')
                    ee=None
                    if (path/'solution.smi').exists():
                        ee=launch([PYTHON,'-u',str(SOURCE/'evaluate_type4.py'),task,str(path),'--gpu',str(gpu)],env,log,gpu,task,'evaluation')
                finish(task,path,ae,ee)
            worker_state(gpu,phase='complete')
        with guard: save()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(worker,1,True),pool.submit(worker,4),pool.submit(worker,6)]
            for future in concurrent.futures.as_completed(futures):
                try: future.result()
                except Exception as exc:
                    with guard:
                        state.setdefault('worker_errors',[]).append(repr(exc));save()
                    print('WORKER ERROR',repr(exc),flush=True)
        with guard:
            state['state']='complete' if len(state['finished'])==340 else 'needs_attention';save()

if __name__=='__main__': main()
