from pathlib import Path
import json,subprocess,time,shutil,fcntl,hashlib,types
r=Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929')
ids=['smdd_004_BCL6_20','smdd_004_BRD2_3','smdd_004_DHFR_16']
assert subprocess.check_output(['systemctl','--user','show','smdd-type4-parallel.service','-p','ActiveState','--value'],text=True).strip()=='inactive'
state=json.loads((r/'parallel_status.json').read_text())
assert not any(state['active'].values())
assert set(state['blocked']['agentdrug'])==set(ids)
assert len(list((r/'chatdrug/records').glob('*.json')))==340
assert len(list((r/'agentdrug/records').glob('*.json')))==337
for tid in ids:assert not (r/'agentdrug/records'/f'{tid}.json').exists()
locks=[]
for method in ['chatdrug','agentdrug']:
 f=(r/method/'batch.lock').open('a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
original=(r/'transport_adapter.py').read_text()
line=" p=subprocess.run(SSH+['/opt/miniconda3/bin/python '+REMOTE],input=json.dumps(body),text=True,capture_output=True,timeout=1100)"
assert original.count(line)==1
replacement=""" for attempt in range(6):
  p=subprocess.run(SSH+['/opt/miniconda3/bin/python '+REMOTE],input=json.dumps(body),text=True,capture_output=True,timeout=1100)
  handshake_failure=p.returncode==255 and not p.stdout.strip() and ('kex_exchange_identification:' in p.stderr or 'ssh_exchange_identification:' in p.stderr)
  if not handshake_failure or attempt==5:break
  time.sleep(min(2**attempt,16))"""
updated=original.replace('import json,subprocess,types','import json,subprocess,types,time').replace(line,replacement)
compile(updated,'transport_adapter.py','exec')
ns={};exec(compile(updated,'<transport-test>','exec'),ns)
calls=[]
responses=[types.SimpleNamespace(returncode=255,stdout='',stderr='kex_exchange_identification: read: Connection reset by peer'),types.SimpleNamespace(returncode=0,stdout='{"choices":[{}]}',stderr='')]
def fake(*args,**kwargs):calls.append(kwargs);return responses.pop(0)
ns['subprocess']=types.SimpleNamespace(run=fake);ns['time']=types.SimpleNamespace(sleep=lambda x:None)
ns['request']([{'role':'user','content':'test'}]);assert len(calls)==2 and calls[0]['input']==calls[1]['input']
responses[:]=[types.SimpleNamespace(returncode=255,stdout='',stderr='Connection closed after authentication')];calls.clear()
try:ns['request']([{'role':'user','content':'test'}]);raise AssertionError('Expected no retry')
except RuntimeError:assert len(calls)==1
archive=r/'agentdrug/retry_archive'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());archive.mkdir(parents=True)
shutil.copy2(r/'parallel_status.json',archive/'parallel_status.before.json')
shutil.copy2(r/'transport_adapter.py',archive/'transport_adapter.before.py')
moved=[]
for tid in ids:
 for section in ['run','evaluator','logs']:
  source=r/'agentdrug'/section/(tid+'.log' if section=='logs' else tid)
  if source.exists():
   assert source.resolve().is_relative_to((r/'agentdrug').resolve())
   target=archive/section/source.name;target.parent.mkdir(parents=True,exist_ok=True);source.rename(target);moved.append(str(target.relative_to(archive)))
(archive/'manifest.json').write_text(json.dumps({'tasks':ids,'reason':'user-authorized rerun after SSH handshake interruption','original_outputs':moved,'created':time.time(),'new_transport_sha256':hashlib.sha256(updated.encode()).hexdigest()},indent=2))
tmp=r/'transport_adapter.py.new';tmp.write_text(updated);tmp.replace(r/'transport_adapter.py')
state['blocked']['agentdrug']={};state['state']='retry_requested';state['updated']=time.time()
tmp=r/'parallel_status.json.tmp';tmp.write_text(json.dumps(state,indent=2));tmp.replace(r/'parallel_status.json')
for f in locks:f.close()
subprocess.run(['systemctl','--user','start','smdd-type4-parallel.service'],check=True)
print('ARCHIVE',archive)
print('REQUEUED',ids)
print('TESTED: handshake-only retries; request body unchanged; no retries after uncertain delivery')
