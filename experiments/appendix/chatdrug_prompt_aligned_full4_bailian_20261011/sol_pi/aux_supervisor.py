from pathlib import Path
import json,time,subprocess,os
ROOT=Path(__file__).resolve().parent
PY='/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python'
pid=json.loads((ROOT/'aux_launch.json').read_text())['pid'];restarts=[]
def dump(v):
 p=ROOT/'aux_supervisor_state.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2));t.replace(p)
def alive(pid):
 try:
  p=Path('/proc')/str(pid);return (p/'stat').read_text().split()[2]!='Z' and (p/'cwd').resolve()==ROOT and b'auxiliary.py' in (p/'cmdline').read_bytes()
 except (FileNotFoundError,PermissionError):return False
while True:
 if alive(pid):dump(dict(phase='watching',pid=pid,restarts=restarts,time=time.time()));time.sleep(15);continue
 state=json.loads((ROOT/'aux_state.json').read_text()) if (ROOT/'aux_state.json').exists() else {}
 if state.get('phase')=='complete':dump(dict(phase='complete',time=time.time()));break
 trace=(ROOT/'aux_error.log').read_text() if (ROOT/'aux_error.log').exists() else ''
 permanent=any(s in trace for s in ('AssertionError','TypeError','KeyError','ValueError','SyntaxError','ImportError'))
 infra=not trace or any(s in trace for s in ('ConnectionError','TimeoutError','OSError','BrokenPipeError','MemoryError'))
 if permanent or not infra or len(restarts)>=3:
  (ROOT/'pause.request').write_text('Aux supervisor blocked; inspect aux_error.log');dump(dict(phase='blocked',state=state,time=time.time()));break
 time.sleep(30*2**len(restarts))
 with (ROOT/'aux_driver.log').open('a') as log:p=subprocess.Popen([PY,'-u','auxiliary.py'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))
 pid=p.pid;restarts.append(dict(pid=pid,time=time.time()))
