"""Sequential, locked Type4 queue. Never reset a started task's budget."""
from pathlib import Path
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from smdd_backends import ROOT, INSTALL
from prepare_type4 import prepare
from runtime_safety import read_json_record, require_disk, ResourceUnavailable,wait_for_gpu
from type4_resume_plan import build_plan

RUN = os.environ.get('LIDDIA_RUN_NAME','full_type4_flowfix1')
if not RUN or Path(RUN).name!=RUN or RUN in ('.','..'):
    raise ValueError('Invalid run name')
OUT = ROOT/'runs'/RUN
OUT.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, obj):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False))
    tmp.replace(path)


def read(path):
    return read_json_record(path)


def main():
    with (OUT/'batch.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_disk(OUT,minimum_gib=50)
        manifest_path=OUT/'manifest.json'
        source=OUT/'source'
        if not manifest_path.exists():
            tasks=sorted(p.name for p in (ROOT/'benchmark/tasks').glob('smdd_004*') if p.is_dir())
            if len(tasks)!=340:
                raise RuntimeError('Expected 340 Type4 tasks, found '+str(len(tasks)))
            parent=os.environ.get('LIDDIA_PARENT_RUN')
            resume=None
            if parent:
                if Path(parent).name!=parent or parent in ('.','..') or parent==RUN:
                    raise ValueError('Invalid parent run')
                resume=build_plan(tasks,ROOT/'runs'/parent)
                priority=list(resume.get('continuations',{}))+list(resume['evaluation_only'])
                tasks=priority+[t for t in tasks if t not in priority]
            failures={}
            with tempfile.TemporaryDirectory() as tmp:
                for task in tasks:
                    try:
                        prepare(ROOT/'benchmark/tasks'/task,Path(tmp)/task)
                    except Exception as exc:
                        failures[task]=str(exc)
            save(OUT/'preflight.json',{'tasks':len(tasks),'failures':failures,'time':now()})
            if failures:
                raise RuntimeError('Public input preflight failed; see preflight.json')
            source.mkdir(exist_ok=True)
            names=['run_liddia_type4.py','liddia_action_parser.py','liddia_flow.py',
                   'code_worker.py','smdd_liddia_tools.py','smdd_backends.py',
                   'prepare_type4.py','evaluate_type4.py','smdd_eval_bridge.py','run_type4_batch.py',
                   'runtime_safety.py','pocket_runtime.py','type4_resume_plan.py','restore_liddia_state.py']
            for name in names:
                shutil.copy2(INSTALL/name,source/name)
            save(manifest_path,{'run':RUN,'created':now(),'tasks':tasks,'execution':'sequential',
                 'admet_per_task':15,'boltz_per_task':8,'llm_per_task':100,
                 'vina_enabled':False,'boltz_gpu':1,'pocket_gpu':3,
                 'pilot_reused':False,'resume':resume,'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')},
                 'task_hashes':{t:hashlib.sha256((ROOT/'benchmark/tasks'/t/'task.yaml').read_bytes()).hexdigest() for t in tasks}})
        manifest=read(manifest_path)
        for name,digest in manifest['source_hashes'].items():
            if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Frozen source changed: '+name)
            if hashlib.sha256((INSTALL/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Installed code differs from frozen run; use a new LIDDIA_RUN_NAME to preserve experiment provenance: '+name)
        tasks=manifest['tasks']
        previous=read(OUT/'batch_status.json') or {}
        resume=manifest.get('resume') or {}
        finished=previous.get('finished',dict(resume.get('inherited',{})))
        state={'run':RUN,'pid':os.getpid(),'state':'running','total':len(tasks),'current':None,'finished':finished}
        def update():
            state.update(updated=now(),completed=len(finished),remaining=len(tasks)-len(finished))
            save(OUT/'batch_status.json',state)
        python=str(INSTALL/'envs/liddia/bin/python')
        env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        for task in tasks:
            if task in finished:
                continue
            try:
                require_disk(OUT,minimum_gib=50)
            except ResourceUnavailable as exc:
                state.update(state='resource_blocked',current=None,phase=None,error=str(exc));update()
                return
            task_out=OUT/task
            if task_out.exists():
                finished[task]={'status':'interrupted_existing_output','time':now(),
                                'agent':read(task_out/'agent_result.json'),
                                'evaluation':read(task_out/'evaluation/result.json')}
                update()
                continue
            state.update(current=task,state='waiting_resources',phase='waiting_gpu');update()
            wait_for_gpu(1,OUT/'resource_wait.json')
            state['state']='running'
            state.update(current=task,phase='agent',task_started=now());update()
            print(now(),task,'START',flush=True)
            with (OUT/(task+'.launcher.log')).open('w') as log:
                eval_source=resume.get('evaluation_only',{}).get(task)
                if eval_source:
                    original=Path(eval_source['source'])
                    if hashlib.sha256((original/'solution.smi').read_bytes()).hexdigest()!=eval_source['solution_sha256']:
                        raise RuntimeError('Original submission changed: '+task)
                    task_out.mkdir(exist_ok=False)
                    for name in ('solution.smi','agent_result.json','protocol.json','budget.jsonl'):
                        if (original/name).exists():shutil.copy2(original/name,task_out/name)
                    save(task_out/'reuse.json',{'source':str(original),'mode':'evaluation_only','agent_rerun':False})
                    agent_exit=None
                else:
                    continuation=resume.get('continuations',{}).get(task)
                    if continuation:
                        original=Path(continuation['source'])
                        task_out.mkdir(exist_ok=False)
                        for name in ('agent_result.json','protocol.json','budget.jsonl','llm_calls.json','molecule_sets.json','trajectory.json'):
                            shutil.copy2(original/name,task_out/name)
                        shutil.copytree(original/'public',task_out/'public')
                        save(task_out/'resume_origin.json',{'source':str(original),'budget_preserved':True})
                    process=subprocess.run([python,'-u',str(source/'run_liddia_type4.py'),'--task',task,'--run',RUN,'--gpu','1'],
                                           cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT) if not continuation else subprocess.run(
                        [python,'-u',str(source/'run_liddia_type4.py'),'--task',task,'--run',RUN,'--gpu','1','--resume'],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
                    agent_exit=process.returncode
                agent=read(task_out/'agent_result.json')
                evaluation_exit=None
                if (task_out/'solution.smi').exists():
                    state['phase']='evaluation';update()
                    evaluated=subprocess.run([python,'-u',str(source/'evaluate_type4.py'),task,str(task_out),'--gpu','1'],
                                             cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
                    evaluation_exit=evaluated.returncode
            evaluation=read(task_out/'evaluation/result.json')
            finished[task]={'agent_exit':agent_exit,'evaluation_exit':evaluation_exit,
                            'mode':'evaluation_only' if eval_source else 'agent_and_evaluation',
                            'agent_status':agent.get('status') if agent else 'startup_failure',
                            'budget_used':agent.get('budget_used') if agent else None,
                            'evaluation_status':evaluation.get('status') if evaluation else None,'time':now()}
            update()
            print(now(),task,'END',json.dumps(finished[task]),flush=True)
            if agent and agent.get('status')=='resource_blocked':
                state.update(state='resource_blocked',phase=None,error=agent.get('error'));update()
                return
        state.update(state='complete',current=None,phase=None);update()


if __name__=='__main__':
    try:
        main()
    except ResourceUnavailable as exc:
        state=read(OUT/'batch_status.json') or {}
        state.update(state='resource_blocked',error=str(exc),updated=now())
        save(OUT/'batch_status.json',state)
        print(str(exc),flush=True)
