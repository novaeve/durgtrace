import json,os,subprocess,time,urllib.request,resource
_limit_soft,_limit_hard=resource.getrlimit(resource.RLIMIT_NOFILE);resource.setrlimit(resource.RLIMIT_NOFILE,(min(65536,_limit_hard),_limit_hard))
from pathlib import Path
R=Path(__file__).resolve().parent;B=R/'bundle'
def dump(v):
 p=R/'watchdog_status.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2));t.replace(p)
def alive(pid):
 try:
  p=Path('/proc')/str(pid);return (p/'cwd').resolve()==R and (p/'stat').read_text().split()[2]!='Z'
 except (FileNotFoundError,PermissionError,ProcessLookupError):return False
def environment():
 env=dict(os.environ,PATH=str(B/'node/bin')+':'+str(B/'isolated_env/bin')+':'+os.environ.get('PATH',''),LD_LIBRARY_PATH=str(B/'node/lib')+':'+os.environ.get('LD_LIBRARY_PATH',''),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENSSL_CONF='/dev/null')
 if (R/'sanitized_network_env.json').exists():
  for k in list(env):
   if k.lower() in ['http_proxy','https_proxy','all_proxy','no_proxy']:env.pop(k)
  env['NO_PROXY']='127.0.0.1,localhost';env['no_proxy']=env['NO_PROXY']
 return env
restarts=[]
while True:
 status=json.loads((R/'status.json').read_text()) if (R/'status.json').exists() else {}
 if status.get('phase')=='complete':dump(dict(phase='complete',time=time.time(),proxy_restarts=restarts));break
 wp=int((R/'worker.pid').read_text());pp=int((R/'proxy.pid').read_text())
 if not alive(wp):
  dump(dict(phase='worker_stopped_requires_review',time=time.time(),worker_pid=wp,policy='Do not rerun chemical failures or still-running native children blindly'));break
 if not alive(pp):
  if len(restarts)>=5:
   (R/'pause.request').write_text('Proxy restart budget exhausted');dump(dict(phase='proxy_blocked',time=time.time()));break
  time.sleep(min(60,10*(len(restarts)+1)))
  with (R/'proxy.log').open('ab') as log:p=subprocess.Popen([str(B/'isolated_env/bin/bench-run'),'-u',str(R/'launch_proxy.py')],cwd=R,env=environment(),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  (R/'proxy.pid').write_text(str(p.pid));restarts.append(dict(pid=p.pid,time=time.time()))
 dump(dict(phase='watching',worker_pid=wp,proxy_pid=int((R/'proxy.pid').read_text()),time=time.time(),proxy_restarts=restarts));time.sleep(20)
