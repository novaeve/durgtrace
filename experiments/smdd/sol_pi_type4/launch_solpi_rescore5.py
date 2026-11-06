from pathlib import Path
import sys
LOCAL=Path(__file__).resolve().parent
sys.path.insert(0,str(LOCAL.parent/'molclaw-type4-a100-20261003'))
from remote import connect,py
ROOT='/yimin/zlc/sol_pi_type4_20261004'
BATCH=ROOT+'/rescore5_20261008'
client=connect()
try:
 py(client,"from pathlib import Path\np=Path("+repr(BATCH)+")\nassert not p.exists(), 'Batch exists: inspect before restarting'\np.mkdir(mode=0o700)\n")
 sftp=client.open_sftp()
 sftp.put(str(LOCAL/'solpi_rescore5_driver.py'),BATCH+'/driver.py')
 sftp.put(str(LOCAL.parent/'molclaw-type4-a100-20261003/molclaw_rescore_boltz.py'),BATCH+'/boltz_transport.py')
 sftp.close()
 py(client,r"""
from pathlib import Path
import json,hashlib,shutil,subprocess,time
r=Path('/yimin/zlc/sol_pi_type4_20261004');batch=r/'rescore5_20261008';mol=Path('/yimin/zlc/molclaw_type4_20261003')
expected={'smdd_004_ACE_8','smdd_004_ALK_2','smdd_004_ALK_3','smdd_004_ALK_4','smdd_004_CDK2_11'}
records={p.parent.name:p for p in (r/'runs/solpi').glob('*/record.json') if json.loads(p.read_text())['evaluation']=='errored'}
assert set(records)==expected
assert len(list((r/'runs/solpi').glob('*/record.json')))==340
assert subprocess.getoutput('systemctl --user is-active sol-pi-type4-a100.service').strip()=='inactive'
assert shutil.disk_usage(r).free>50*1024**3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(r/'evaluate.py')=='d627897bb775af951d74e9a539e3cb6a49a0e2698a0406544bd4d55e4545a4c1'
manifest={'time':time.time(),'tasks':{},'sample_count':10,'seed':42,'workers':2,'download_timeout':[30,180],'source_hashes':{name:sha(r/name) for name in ['runtime.py','evaluate.py','gpu_slots.py','smdd_eval_bridge.py']},'all_record_hashes':{str(p.relative_to(r)):sha(p) for p in (r/'runs/solpi').glob('*/record.json')}}
for name in ['workers','logs','original_evaluation','original_records']:(batch/name).mkdir()
for tid,p in sorted(records.items()):
 out=p.parent;solution=out/'solution.smi';assert solution.exists() and solution.read_text().strip()
 dest=batch/'runs/solpi'/tid;dest.mkdir(parents=True);shutil.copy2(solution,dest/'solution.smi')
 shutil.copy2(p,batch/'original_records'/f'{tid}.json')
 manifest['tasks'][tid]={'submission_sha256':sha(solution),'record_sha256':sha(p),'evaluation_sha256':sha(out/'evaluation/result.json')}
for name in ['driver.py','boltz_transport.py']:compile((batch/name).read_text(),name,'exec')
python=mol/'rootfs/opt/conda/bin/python';env=dict(__import__('os').environ,PYTHONNOUSERSITE='1',LD_LIBRARY_PATH=str(mol/'rootfs/opt/conda/lib'))
probe=subprocess.run([str(python),str(batch/'boltz_transport.py'),'--transport-self-test'],capture_output=True,text=True,env=env,timeout=20)
print(probe.stdout);assert probe.returncode==0,probe.stderr
(batch/'manifest.json').write_text(json.dumps(manifest,indent=2))
(batch/'preflight.json').write_text(json.dumps({'time':time.time(),'transport_test':probe.stdout,'all_five_submissions_frozen':True},indent=2))
unit_name='sol-pi-type4-rescore5-20261008.service';unit=Path.home()/'.config/systemd/user'/unit_name;assert not unit.exists();unit.parent.mkdir(parents=True,exist_ok=True)
unit.write_text('[Unit]\nDescription=SoL-Pi Type4 five frozen-submission rescores\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory='+str(batch)+'\nExecStart='+str(python)+' -u '+str(batch/'driver.py')+'\nEnvironment=PYTHONNOUSERSITE=1\nEnvironment=LD_LIBRARY_PATH='+str(mol/'rootfs/opt/conda/lib')+'\nEnvironment=OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\nRestart=on-failure\nRestartSec=30\nKillMode=control-group\nTimeoutStopSec=45\nStandardOutput=append:'+str(batch/'driver.log')+'\nStandardError=append:'+str(batch/'driver.log')+'\n\n[Install]\nWantedBy=default.target\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now',unit_name],check=True)
print('LAUNCHED',str(batch),5)
print(subprocess.getoutput('systemctl --user show '+unit_name+' -p ActiveState -p SubState -p MainPID -p NRestarts'))
""")
finally:client.close()
