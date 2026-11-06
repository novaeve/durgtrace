from pathlib import Path
import sys
LOCAL=Path(__file__).resolve().parent
sys.path.insert(0,str(LOCAL.parent/'gpu-scheduling-20261001'))
from manage import connect,execute
ROOT='/data2/chenfuxin/smdd_deepseek_codex_type4_20261004'
BATCH=ROOT+'/codex_selected_retry_20261007'
c=connect('gpu')
try:
 execute(c,"from pathlib import Path\np=Path("+repr(BATCH)+")\nassert not p.exists(), 'Batch already exists; inspect instead of relaunching'\np.mkdir(mode=0o700)\n")
 s=c.open_sftp()
 s.put(str(LOCAL/'codex_retry_selected.py'),BATCH+'/driver.py')
 s.put(str(LOCAL.parent/'molclaw-type4-a100-20261003/molclaw_rescore_boltz.py'),BATCH+'/boltz_transport.py')
 s.close()
 execute(c,r'''
from pathlib import Path
import hashlib,json,shutil,subprocess,time,os
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');batch=r/'codex_selected_retry_20261007'
python=Path('/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python')
unit_name='smdd-codex-selected-retry-20261007.service'
unit=Path.home()/'.config/systemd/user'/unit_name;assert not unit.exists()
assert shutil.disk_usage(r).free>=50*1024**3
status=json.loads((r/'scheduler_status.json').read_text());assert status['state']=='complete' and not any(status['active'].values())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(r/'run.py')=='1c7ff81a0d09e8ee7f96175daaef64308e57333cce077621fcefc27ff26b522a'
assert sha(r/'runtime.py')=='663c9743e3f26266f99c7bc26fc43c5f069acb92158033e6e36080e2fc0a0d98'
manifest={'time':time.time(),'model':'deepseek-v4.1-flash','enable_thinking':False,'temperature':1,'max_model_calls':100,'max_tokens':10000000,'boltz_budget':8,'admet_budget':15,'seed':42,'samples':10,'tasks':{},'source_hashes':{},'all_terminal_hashes':{str(p.relative_to(r)):sha(p) for p in (r/'runs').glob('*/*/record.json')}}
for name in ['runtime.py','run.py','gpu_slots.py','evaluate.py','smdd_eval_bridge.py']:
 manifest['source_hashes'][name]=sha(r/name)
for name in ['logs','workers','original_runs','original_evaluation','original_records']:(batch/name).mkdir()
for tid,mode in [('smdd_004_EHMT2_1','rerun'),('smdd_004_EHMT2_6','rerun'),('smdd_004_DHFR_3','rescore')]:
 out=r/'runs/codex'/tid;rec=json.loads((out/'record.json').read_text())
 assert rec['evaluation']==('not_evaluated' if mode=='rerun' else 'errored')
 meta={'mode':mode,'record_sha256':sha(out/'record.json')}
 shutil.copy2(out/'record.json',batch/'original_records'/f'{tid}.json')
 if mode=='rerun':
  assert not (out/'solution.smi').exists() and not (out/'workspace/solution.smi').exists()
  agent=json.loads((out/'result.json').read_text());assert agent['status']=='error' and 'timed out after 43199' in agent['error']
 else:
  source=out/'solution.smi';assert source.read_text().strip()
  meta['submission_sha256']=sha(source)
  frozen=batch/'runs/codex'/tid;frozen.mkdir(parents=True);shutil.copy2(source,frozen/'solution.smi')
 manifest['tasks'][tid]=meta
for name in ['driver.py','boltz_transport.py']:compile((batch/name).read_text(),name,'exec')
test=subprocess.run([str(python),str(batch/'boltz_transport.py'),'--transport-self-test'],capture_output=True,text=True,timeout=20)
print(test.stdout);assert test.returncode==0,test.stderr
probe=subprocess.run([str(python),'-c',"import sys;sys.path.insert(0,"+repr(str(r))+");import runtime,run;from gpu_slots import snapshot;print('RUNTIME_OK GPU_CANDIDATES',snapshot())"],capture_output=True,text=True,timeout=25)
print(probe.stdout);assert probe.returncode==0,probe.stderr
(batch/'manifest.json').write_text(json.dumps(manifest,indent=2))
(batch/'preflight.json').write_text(json.dumps({'time':time.time(),'transport':test.stdout,'runtime':probe.stdout,'task_count':3,'nonselected_untouched':True},indent=2))
unit.parent.mkdir(parents=True,exist_ok=True)
unit.write_text('[Unit]\nDescription=SMDD Codex two disk-timeout reruns and one rescore\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory='+str(batch)+'\nExecStart='+str(python)+' -u '+str(batch/'driver.py')+'\nEnvironment=OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\nRestart=on-failure\nRestartSec=30\nKillMode=control-group\nTimeoutStopSec=45\nStandardOutput=append:'+str(batch/'driver.log')+'\nStandardError=append:'+str(batch/'driver.log')+'\n\n[Install]\nWantedBy=default.target\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now',unit_name],check=True)
print('LAUNCHED',str(batch))
print(subprocess.getoutput('systemctl --user show '+unit_name+' -p ActiveState -p SubState -p MainPID -p NRestarts'))
''')
finally:c.close()
