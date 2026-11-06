from pathlib import Path
import subprocess,os,json,sys
root=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004')
batch=root/'codex_selected_retry_20261007';unit='smdd-codex-selected-retry-20261007.service'
assert (batch/'manifest.json').exists() and (batch/'preflight.json').exists()
env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
for args in [['systemctl','--user','daemon-reload'],['systemctl','--user','enable','--now',unit],['systemctl','--user','show',unit,'-p','ActiveState','-p','SubState','-p','MainPID','-p','NRestarts']]:
 result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=40)
 print('CMD',args,'RC',result.returncode,'STDOUT',result.stdout,'STDERR',result.stderr)
 if result.returncode:raise RuntimeError('Service startup failed; prepared batch retained')
