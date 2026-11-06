from pathlib import Path
import json,sys,shlex
from remote import connect,run,py,ROOT as LOCAL

BASE='/yimin/zlc/molclaw_type4_20261003'
BATCH=BASE+'/rescore9_20261007'
UNIT='molclaw-type4-rescore9-20261007'
client=connect()
try:
    py(client,"from pathlib import Path\np=Path("+repr(BATCH)+")\nassert not p.exists(), 'Rescore batch already exists; inspect before relaunch'\np.mkdir(mode=0o700)")
    sftp=client.open_sftp()
    for source,target in [('molclaw_rescore_driver.py','driver.py'),('molclaw_rescore_boltz.py','boltz_transport.py')]:
        sftp.put(str(LOCAL/source),BATCH+'/'+target)
    sftp.close()
    code=r'''
from pathlib import Path
import collections,hashlib,json,shutil,subprocess,time
base=Path('/yimin/zlc/molclaw_type4_20261003');batch=base/'rescore9_20261007'
expected={'smdd_004_CCR2_17','smdd_004_CCR2_2','smdd_004_CCR2_22','smdd_004_CDK2_0','smdd_004_CDK2_1','smdd_004_CDK2_10','smdd_004_CDK2_11','smdd_004_CDK2_12','smdd_004_CDK2_15'}
records={p.parent.name:p for p in (base/'evaluation/molclaw').glob('*/result.json') if json.loads(p.read_text()).get('status')=='errored'}
assert set(records)==expected,set(records)
assert subprocess.getoutput('systemctl --user is-active molclaw-type4-a100.service').strip()=='inactive'
assert shutil.disk_usage(base).free>50*1024**3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'created':time.time(),'method':'molclaw','workers':2,'sample_count':10,'seed':42,'network_timeout_download':[30,180],'network_timeout_ticket':[30,60],'tasks':{},'sources':{}}
for name in ['evaluate.py','eval_bridge.py','runtime.py','gpu_slots.py']:
 manifest['sources'][name]=sha(base/name)
for name in ['driver.py','boltz_transport.py']:
 compile((batch/name).read_text(),name,'exec')
 manifest['sources'][name]=sha(batch/name)
(batch/'workers').mkdir();(batch/'original_evaluation').mkdir();(batch/'original_results').mkdir()
for tid,p in sorted(records.items()):
 source=base/'runs/molclaw'/tid/'solution.smi'
 assert source.exists() and source.read_text().strip()
 dest=batch/'runs/molclaw'/tid/'solution.smi';dest.parent.mkdir(parents=True);shutil.copy2(source,dest)
 shutil.copy2(p,batch/'original_results'/f'{tid}.json')
 manifest['tasks'][tid]={'submission_sha256':sha(source),'original_result_sha256':sha(p)}
for name,target in [('tasks',base/'tasks'),('eval_bridge.py',base/'eval_bridge.py')]:
 (batch/name).symlink_to(target,target_is_directory=target.is_dir())
(batch/'manifest.json').write_text(json.dumps(manifest,indent=2))
python=base/'rootfs/opt/conda/bin/python'
env={'PATH':str(base/'rootfs/opt/conda/bin')+':/usr/bin:/bin','LD_LIBRARY_PATH':str(base/'rootfs/opt/conda/lib'),'PYTHONNOUSERSITE':'1'}
test=subprocess.run([str(python),str(batch/'boltz_transport.py'),'--transport-self-test'],capture_output=True,text=True,env=env,timeout=20)
print(test.stdout);assert test.returncode==0,test.stderr
(batch/'preflight.json').write_text(json.dumps({'time':time.time(),'transport_test':test.stdout,'submission_count':9,'originals_preserved':True},indent=2))
unit=Path.home()/'.config/systemd/user/molclaw-type4-rescore9-20261007.service';assert not unit.exists();unit.parent.mkdir(parents=True,exist_ok=True)
unit.write_text('[Unit]\nDescription=MolClaw SMDD Type4 nine frozen-submission rescores\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory='+str(batch)+'\nEnvironment=PYTHONUNBUFFERED=1\nEnvironment=PYTHONNOUSERSITE=1\nEnvironment=LD_LIBRARY_PATH='+str(base/'rootfs/opt/conda/lib')+'\nExecStart='+str(python)+' '+str(batch/'driver.py')+'\nRestart=on-failure\nRestartSec=30\nKillMode=control-group\nTimeoutStopSec=30\nStandardOutput=append:'+str(batch/'driver.log')+'\nStandardError=append:'+str(batch/'driver.log')+'\n\n[Install]\nWantedBy=default.target\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','molclaw-type4-rescore9-20261007.service'],check=True)
print('LAUNCHED',str(batch),len(manifest['tasks']))
print(subprocess.getoutput('systemctl --user show molclaw-type4-rescore9-20261007.service -p ActiveState -p SubState -p MainPID -p NRestarts'))
'''
    py(client,code)
finally:
    client.close()
