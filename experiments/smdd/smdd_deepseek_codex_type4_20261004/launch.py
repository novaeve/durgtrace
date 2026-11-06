from pathlib import Path
import json,subprocess,hashlib,os
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004')
assert json.loads((r/'preflight/result.json').read_text())['passed']
checks=[]
for p in (r/'preflight').glob('**/api/*.json'):
 d=json.loads(p.read_text());req=d['request'];resp=d.get('response',{})
 assert req['model']=='deepseek-v4.1-flash' and req['enable_thinking'] is False and req['temperature']==1
 assert 'reasoning_effort' not in req and 'reasoning' not in req
 assert resp.get('model')=='deepseek-v4.1-flash'
 checks.append(str(p.relative_to(r)))
assert len(checks)>=6
for p in (r/'upstream/agent_harness').glob('*.py'):
 original=Path('/data2/chenfuxin/smdd_type3_transfer_20260930/upstream/agent_harness')/p.name
 assert p.read_bytes()==original.read_bytes()
manifest={'created':__import__('time').time(),'methods':['deepseek_official_smdd_harness','codex_official_cli_harness'],'tasks_per_method':340,'model':'deepseek-v4.1-flash','enable_thinking':False,'reasoning_effort':'omitted','temperature':1,'budgets':{'admet':15,'boltz':8,'model_turns':100,'cumulative_tokens':10000000,'seed':42,'default_diffusion_samples':10},'concurrency_per_method':4,'gpu_pool':[1,3,4,6],'gpu_max_boltz_processes_per_card':1,'gpu_minimum_free_mib':28000,'gpu_lock_coordination':['liddia_type4','cpu_type4_pool'],'official_upstream':'/data2/chenfuxin/smdd_type3_transfer_20260930/upstream/agent_harness','official_cli':subprocess.check_output([str(r/'bin/codex'),'--version'],text=True).strip(),'reviewer':False,'memory':False,'multi_agent':False,'credentials':'read only on existing credential host; not copied','public_only_inputs':['description','complex.pdb','reference.sdf'],'evaluation':'same original smdd-evals evaluator rootfs; Boltz transport only','preflight_checked_actual_requests':checks,'hashes':{str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list(r.glob('*.py'))+list((r/'upstream/agent_harness').glob('*.py'))}}
(r/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(subprocess.getoutput('loginctl show-user chenfuxin -p Linger'))
unit=Path.home()/'.config/systemd/user/smdd-deepseek-codex-type4-20261004.service';unit.parent.mkdir(parents=True,exist_ok=True)
if (r/'scheduler_status.json').exists():
 state=json.loads((r/'scheduler_status.json').read_text())
 if Path('/proc',str(state['pid'])).exists():raise RuntimeError('Existing scheduler is already running')
unit.write_text('[Unit]\nDescription=SMDD Type4 DeepSeek official harness and Codex full340\n[Service]\nType=simple\nWorkingDirectory='+str(r)+'\nExecStart=/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python -u '+str(r/'scheduler.py')+'\nEnvironment=OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\nRestart=on-failure\nRestartSec=30\nKillMode=process\nStandardOutput=append:'+str(r/'scheduler.log')+'\nStandardError=append:'+str(r/'scheduler.log')+'\n[Install]\nWantedBy=default.target\n')
linger=subprocess.getoutput('loginctl show-user chenfuxin -p Linger')
if linger.strip()=='Linger=yes':
 subprocess.run(['systemctl','--user','daemon-reload'],check=True)
 subprocess.run(['systemctl','--user','enable','--now',unit.name],check=True)
 print(subprocess.getoutput('systemctl --user show '+unit.name+' -p ActiveState -p MainPID'))
else:
 with (r/'scheduler.log').open('a') as log:
  proc=subprocess.Popen(['nohup','/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python','-u',str(r/'scheduler.py')],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'))
 print('DETACHED_PERSISTENT_SCHEDULER_PID',proc.pid)
print('ACTUAL_NONTHINKING_REQUESTS_VERIFIED',len(checks))
