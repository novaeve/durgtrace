from pathlib import Path
import hashlib,json,subprocess,time,datetime
base=Path('/yimin/zlc/molclaw_type4_20261003');batch=base/'rescore9_20261007'
manifest=json.loads((batch/'manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
print('TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
print('SERVICE',subprocess.getoutput('systemctl --user show molclaw-type4-rescore9-20261007.service -p ActiveState -p SubState -p MainPID -p NRestarts'))
print('STATUS',(batch/'status.json').read_text() if (batch/'status.json').exists() else 'pending')
print('SOURCES_UNCHANGED',all(sha(base/name)==value for name,value in manifest['sources'].items() if name not in ['driver.py','boltz_transport.py']))
print('SUBMISSIONS_UNCHANGED',all(sha(base/'runs/molclaw'/tid/'solution.smi')==meta['submission_sha256'] for tid,meta in manifest['tasks'].items()))
print('LOG',(batch/'driver.log').read_text(errors='replace')[-3500:])
for task in (batch/'evaluation/molclaw').iterdir():
 for log in (task/'queue').rglob('boltz.log'):
  text=log.read_text(errors='replace');print('BOLTZ',task.name,text[-1400:])
 for path in (task/'queue').rglob('resource_wait.json'):print('RESOURCE_WAIT',task.name,path.read_text())
print('SOL_SERVICE',subprocess.getoutput('systemctl --user show sol-pi-type4-a100.service -p ActiveState -p SubState -p MainPID -p NRestarts'))
print('GPU',subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
