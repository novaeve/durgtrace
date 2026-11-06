"""Independent keeper for gateways, SSH tunnels and the combined-report monitor."""
import fcntl,importlib.util,json,os,signal,subprocess,threading,time,traceback
from pathlib import Path
from resilience_common import read,write,alive,start
ROOT=Path(__file__).resolve().parent;PY=ROOT/'runtime/chatdrug_generalization_20260920/venv/bin/python'
assert ROOT==Path('/home/chenfuxin/glm53flash_three_settings_20261011')
probe_at={}
probe_running=set()
gpu_check_at=0;gpu_check_running=False

def recover_gateway(port,script):
 import requests
 try:health=requests.get(f'http://127.0.0.1:{port}/health',timeout=3).json()
 except (requests.RequestException,ValueError):return None
 if not health.get('halted') or time.time()<probe_at.get(port,0):return None
 probe_at[port]=time.time()+300
 # Probe within the CPU host; credentials never leave the configured provider route.
 spec=importlib.util.spec_from_file_location('resilience_provider_probe',ROOT/'gateway.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 body={'model':module.MODEL,'temperature':0,'reasoning_effort':'low','max_tokens':256,'n':1,
  'messages':[{'role':'user','content':'Reply exactly OK.'}]}
 for _ in range(2):
  try:
   response=requests.post(module.BASE+'/chat/completions',json=body,headers={'Authorization':'Bearer '+module.KEY},timeout=(15,60),allow_redirects=False)
   try:
    if response.status_code!=200:return None
    obj=response.json()
    if not isinstance(obj,dict) or obj.get('error'):return None
    obj=module.canonicalize_model(obj,body,set())
    if obj.get('model')!=module.MODEL or not obj.get('choices'):return None
   finally:response.close()
  except (requests.RequestException,ValueError):return None
 fresh=requests.get(f'http://127.0.0.1:{port}/health',timeout=3).json()
 if read(ROOT/'run_control.json',{}).get('paused_by_user') or (ROOT/'maintenance.json').exists():return None
 if not fresh.get('halted'):return 'already_recovered'
 if fresh.get('halted')!=health['halted'] or fresh.get('active',0):return None
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:args=(proc/'cmdline').read_bytes().split(b'\0')
  except OSError:continue
  if str(ROOT/script).encode() in args:os.kill(int(proc.name),signal.SIGTERM)
 time.sleep(.5)
 start(ROOT,[str(PY),'-u',str(ROOT/script)],script)
 with (ROOT/'resilience_events.jsonl').open('a') as f:f.write(json.dumps({'event':'gateway_verified_recovery','port':port,'reason':health['halted'],'time':time.time()})+'\n')
 return 'restarted_after_upstream_verification'

def probe_background(port,script):
 try:recover_gateway(port,script)
 except Exception:
  with (ROOT/'resilience_cpu_errors.log').open('a') as f:f.write(str(time.time())+'\n'+traceback.format_exc()+'\n')
 finally:probe_running.discard(port)

def bootstrap_gpu_background():
 global gpu_check_running
 try:
  from monitor import SSH,GPU
  subprocess.run(SSH+['/usr/bin/python3 '+GPU+'/bootstrap_resilience.py'],check=True,timeout=45,stdout=subprocess.DEVNULL)
 except Exception:
  with (ROOT/'resilience_cpu_errors.log').open('a') as f:f.write(str(time.time())+'\nGPU bootstrap: '+traceback.format_exc()+'\n')
 finally:gpu_check_running=False

def tick():
 global gpu_check_at,gpu_check_running
 report={'pid':os.getpid(),'time':time.time(),'phase':'watching','started':[]}
 if read(ROOT/'run_control.json',{}).get('paused_by_user') or (ROOT/'maintenance.json').exists():
  report['phase']='manual_pause';write(ROOT/'resilience_cpu_state.json',report);return
 from monitor import ensure_services
 ensure_services()
 # Also recover the GPU watcher after boot/crash if that host's system cron is unavailable.
 if not gpu_check_running and time.time()>=gpu_check_at:
  gpu_check_running=True;gpu_check_at=time.time()+60
  threading.Thread(target=bootstrap_gpu_background,daemon=True).start()
 for port,script in ((18853,'gateway.py'),(18855,'gateway_claw.py')):
  if port not in probe_running and time.time()>=probe_at.get(port,0):
   probe_running.add(port);threading.Thread(target=probe_background,args=(port,script),daemon=True).start()
 heartbeat=read(ROOT/'monitor_heartbeat.json',{})
 if heartbeat and time.time()-heartbeat.get('time',0)>360 and alive(ROOT/'monitor.py'):
  pid=heartbeat.get('pid')
  try:
   args=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\0')
   if str(ROOT/'monitor.py').encode() in args:os.kill(pid,signal.SIGTERM);report['stale_monitor_restarted']=True
  except OSError:pass
 if not alive(ROOT/'monitor.py'):report['started'].append(start(ROOT,[str(PY),'-u',str(ROOT/'monitor.py')],'monitor'))
 write(ROOT/'resilience_cpu_state.json',report)

if __name__=='__main__':
 with (ROOT/'resilience_cpu.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while True:
   try:tick()
   except Exception:
    with (ROOT/'resilience_cpu_errors.log').open('a') as f:f.write(str(time.time())+'\n'+traceback.format_exc()+'\n')
   time.sleep(15)
