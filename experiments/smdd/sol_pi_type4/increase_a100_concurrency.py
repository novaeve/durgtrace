from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
from remote import connect,py
LOCAL=Path(__file__).resolve().parent
ROOT='/yimin/zlc/sol_pi_type4_20261004'
client=connect()
try:
 py(client,"from pathlib import Path\nr=Path("+repr(ROOT)+")\nassert (r/'scheduler.py').read_text().count(\"METHODS=['solpi'];WIDTH=4\")==1, 'Inspect current concurrency before applying'\n")
 sftp=client.open_sftp()
 for name in ['scheduler.py','gpu_slots.py']:
  sftp.put(str(LOCAL/'a100'/name),ROOT+'/'+name+'.concurrency_staged')
 sftp.put(str(LOCAL/'test_gpu_slots_concurrency.py'),ROOT+'/test_gpu_slots_concurrency.py')
 sftp.close()
 py(client,r'''
from pathlib import Path
import hashlib,json,subprocess,shutil,time,datetime
r=Path('/yimin/zlc/sol_pi_type4_20261004');mol=Path('/yimin/zlc/molclaw_type4_20261003')
unit='sol-pi-type4-a100.service'
assert subprocess.getoutput('systemctl --user show '+unit+' -p KillMode --value').strip()=='process'
for other in ['molclaw-type4-a100.service','molclaw-type4-rescore9-20261007.service']:
 assert subprocess.getoutput('systemctl --user is-active '+other).strip()=='inactive'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(r/'scheduler.py')=='4541dd6eedce65b96bfc388b246bd1f33933e7aadebfe0f0ca26c4c6a7313477'
assert sha(r/'gpu_slots.py')=='70ad6703999ba7090c6cb70352e608bbc8023d29e9d2f0172e9336abe4a5a77e'
for name in ['scheduler.py','gpu_slots.py']:
 compile((r/(name+'.concurrency_staged')).read_text(),name,'exec')
python=mol/'rootfs/opt/conda/bin/python'
test=subprocess.run([str(python),str(r/'test_gpu_slots_concurrency.py'),str(r/'gpu_slots.py.concurrency_staged')],capture_output=True,text=True,timeout=30)
print('SLOT_TEST',test.stdout);assert test.returncode==0,test.stderr
snapshot=json.loads((r/'scheduler_status.json').read_text())
active=snapshot['active']['solpi']
records={str(p.relative_to(r)):sha(p) for p in (r/'runs/solpi').glob('*/record.json')}
backup=r/'repairs'/('concurrency_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True)
for name in ['scheduler.py','gpu_slots.py','scheduler_status.json','manifest.json','DEPLOYMENT.md']:
 if (r/name).exists():shutil.copy2(r/name,backup/name)
before={'active':active,'record_hashes':records,'width_before':4,'width_after':8,'gpu_process_limit_per_card':2,'test_output':test.stdout,'time':time.time()}
(backup/'before.json').write_text(json.dumps(before,indent=2))
for name in ['scheduler.py','gpu_slots.py']:(r/(name+'.concurrency_staged')).replace(r/name)
# Only the scheduler process restarts; the unit's KillMode=process preserves workers.
subprocess.run(['systemctl','--user','restart',unit],check=True,timeout=55)
deadline=time.time()+20
while time.time()<deadline:
 status=json.loads((r/'scheduler_status.json').read_text())
 if status.get('concurrency_per_method')==8 and status['pid']!=snapshot['pid']:break
 time.sleep(1)
assert status.get('concurrency_per_method')==8,status
assert status['counts']['solpi']['active']==8,status
assert not status['blocked']['solpi'],status
adopted={it['task']:it for it in status['active']['solpi']}
for item in active:
 assert item['task'] in adopted or (r/'runs/solpi'/item['task']/'record.json').exists(),item
 if item['task'] in adopted:assert adopted[item['task']]['pid']==item['pid'],item
assert all(sha(r/p)==hashval for p,hashval in records.items())
update={'time':time.time(),'backup':str(backup),'agent_workers':8,'prediction_slots_per_gpu':2,'total_prediction_slots':4,'memory_guard_mib':36000,'admission_interval_seconds':90,'existing_workers_preserved':True,'existing_terminal_records_unchanged':True,'sources':{name:sha(r/name) for name in ['scheduler.py','gpu_slots.py']}}
(backup/'result.json').write_text(json.dumps(update,indent=2));(r/'concurrency_update.json').write_text(json.dumps(update,indent=2))
if (r/'manifest.json').exists():
 manifest=json.loads((r/'manifest.json').read_text());manifest['concurrency_update']=update;(r/'manifest.json').write_text(json.dumps(manifest,indent=2))
if (r/'DEPLOYMENT.md').exists():
 with (r/'DEPLOYMENT.md').open('a') as f:f.write('\n2026-10-07 concurrency update: 8 agent workers, 2 shared Boltz slots per A100 (4 total); 90-second admission, 36,000 MiB memory guard and 50 GiB disk reserve preserved. Existing workers adopted without changing terminal results or budgets.\n')
print('UPDATE',json.dumps(update));print('COUNTS',json.dumps(status['counts']));print('ACTIVE',json.dumps(status['active']['solpi']))
''')
finally:client.close()
