from pathlib import Path
import hashlib,json,subprocess,time,datetime
r=Path('/yimin/zlc/sol_pi_type4_20261004');batch=r/'rescore5_20261008'
manifest=json.loads((batch/'manifest.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
print('TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
print('SERVICE',subprocess.getoutput('systemctl --user show sol-pi-type4-rescore5-20261008.service -p ActiveState -p MainPID -p NRestarts'))
print('STATUS',(batch/'status.json').read_text())
print('SUBMISSIONS_UNCHANGED',all(sha(r/'runs/solpi'/tid/'solution.smi')==meta['submission_sha256'] for tid,meta in manifest['tasks'].items()))
print('NONSELECTED_RECORDS_UNCHANGED',all(sha(r/p)==h for p,h in manifest['all_record_hashes'].items() if Path(p).parent.name not in manifest['tasks']))
print('SOURCE_FILES_UNCHANGED',all(sha(r/p)==h for p,h in manifest['source_hashes'].items()))
print('DRIVER_LOG',(batch/'driver.log').read_text(errors='replace')[-1500:])
for tid in manifest['tasks']:
 out=batch/'runs/solpi'/tid
 if not (out/'evaluation').exists():continue
 for p in (out/'evaluation').rglob('boltz.log'):print('BOLTZ',tid,p.read_text(errors='replace')[-950:])
 for p in out.rglob('resource_wait.json'):
  if time.time()-p.stat().st_mtime<90:print('WAIT',tid,p.read_text())
if (batch/'completion.json').exists():print('COMPLETION',(batch/'completion.json').read_text())
