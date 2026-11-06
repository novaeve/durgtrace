import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT=Path('/data2/chenfuxin/liddia_smdd_type4_20260928')
INSTALL=Path('/data2/chenfuxin/agent_reproduction_20260928')
OLD=ROOT/'runs/full_type4_waitresume3'
OUT=ROOT/'runs/full_type4_parallel3'
assert not OUT.exists(), 'Target already exists; reconcile before retry'
OUT.mkdir();source=OUT/'source';shutil.copytree(OLD/'source',source)
shutil.copy2(INSTALL/'parallel_type4.py',source/'parallel_type4.py')

def replace(name,old,new):
    p=source/name;s=p.read_text();assert s.count(old)==1,(name,old,s.count(old));p.write_text(s.replace(old,new))

replace('run_liddia_type4.py',"device='cuda',gpu=3)","device='cuda',gpu=int(os.environ.get('LIDDIA_POCKET_GPU','3')))")
replace('run_liddia_type4.py',"'pocket_gpu':3,","'pocket_gpu':int(os.environ.get('LIDDIA_POCKET_GPU','3')),")
replace('runtime_safety.py','def select_gpu(preferred, minimum_mib=28000):',
'''def select_gpu(preferred, minimum_mib=28000):
    fixed=os.environ.get('LIDDIA_FIXED_GPU')
    if fixed is not None:
        gpu=int(fixed)
        require_gpu(gpu,minimum_mib)
        return gpu''')
with (source/'runtime_safety.py').open('a') as f:
    f.write('''

from contextlib import contextmanager
import fcntl

@contextmanager
def pocket_gpu_lease(gpu):
    from smdd_backends import ROOT
    with (ROOT/f'boltz_gpu{gpu}.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        while True:
            try:
                require_gpu(gpu)
                break
            except ResourceUnavailable:
                time.sleep(60)
        yield
''')
replace('smdd_liddia_tools.py','from runtime_safety import ToolExecutionError, require_disk',
        'from runtime_safety import ToolExecutionError, require_disk, pocket_gpu_lease\nfrom contextlib import nullcontext')
replace('smdd_liddia_tools.py',
'''                subprocess.run(cmd, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=3600)''',
'''                with pocket_gpu_lease(self.gpu) if self.device == 'cuda' else nullcontext():
                    subprocess.run(cmd, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   check=True, timeout=3600)''')
for p in source.glob('*.py'): ast.parse(p.read_text())
sys.path.insert(0,str(source))
from unittest.mock import patch
import runtime_safety as safety
with patch.dict(os.environ,{'LIDDIA_FIXED_GPU':'4'}):
    with patch.object(safety,'require_gpu') as check:
        assert safety.select_gpu(1)==4;check.assert_called_once_with(4,28000)
    with patch.object(safety,'require_gpu',side_effect=safety.ResourceUnavailable('busy')):
        try: safety.select_gpu(1)
        except safety.ResourceUnavailable: pass
        else: raise AssertionError('Pinned GPU must not spill onto another worker')
assert shutil.disk_usage(OUT).free>50*1024**3
parent=json.loads((OLD/'batch_status.json').read_text())['pid']
assert b'run_type4_batch.py' in (Path('/proc')/str(parent)/'cmdline').read_bytes()
os.kill(parent,signal.SIGSTOP)
try:
    for _ in range(30):
        if (Path('/proc')/str(parent)/'stat').read_text().split(') ')[1][0]=='T':break
        time.sleep(.1)
    else: raise RuntimeError('Dispatcher did not stop')
    state=json.loads((OLD/'batch_status.json').read_text())
    task=state['current'];assert state['phase'] in ('agent','evaluation')
    children=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            info=(p/'stat').read_text().split(') ')[1].split()
            cmd=(p/'cmdline').read_bytes()
            if int(info[1])==parent and task.encode() in cmd and info[0]!='Z': children.append(int(p.name))
        except (FileNotFoundError,PermissionError,ProcessLookupError): pass
    assert len(children)==1,children
    inherited={}
    for name,record in state['finished'].items():
        inherited[name]=dict(record,reused_from=record.get('reused_from',str(OLD/name)))
    tasks=json.loads((OLD/'manifest.json').read_text())['tasks']
    pending=[t for t in tasks if t not in inherited and t!=task]
    assert len(set(pending))==len(pending)
    assert len(inherited)+1+len(pending)==340
    assert all(not (OLD/t).exists() for t in pending), 'Unexpected started task'
    manifest={'run':OUT.name,'created':time.time(),'execution':'three independent task workers',
              'gpus':[1,4,6],'tasks':tasks,'inherited':inherited,'pending':pending,
              'adoption':{'task':task,'phase':state['phase'],'child_pid':children[0],
                          'parent_pid':parent,'parent_run':str(OLD),'output':str(OLD/task)},
              'admet_per_task':15,'boltz_per_task':8,'llm_per_task':100,'vina_enabled':False,
              'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')},
              'task_hashes':json.loads((OLD/'manifest.json').read_text())['task_hashes']}
    safety.atomic_json(OUT/'manifest.json',manifest)
    safety.atomic_json(OLD/'parallel_handoff.json',{'successor':str(OUT),'adoption':manifest['adoption'],'time':time.time()})
    with (OUT/'batch.log').open('a') as log:
        proc=subprocess.Popen([str(INSTALL/'envs/liddia/bin/python'),'-u',str(source/'parallel_type4.py')],
                              cwd=source,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
    print(json.dumps({'pid':proc.pid,'inherited':len(inherited),'adopted':task,'pending':len(pending),'run':str(OUT)}))
except BaseException:
    os.kill(parent,signal.SIGCONT)
    raise
