from pathlib import Path
import json,subprocess,time,shutil,fcntl,hashlib
r=Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments/type4_full340_bailian_20260929')
assert subprocess.check_output(['systemctl','--user','show','smdd-type4-parallel.service','-p','ActiveState','--value'],text=True).strip()=='inactive'
state=json.loads((r/'parallel_status.json').read_text());assert not any(state['active'].values())
ids=[]
for p in (r/'chatdrug/records').glob('*.json'):
 d=json.loads(p.read_text())
 if d.get('evaluation')=='errored' and 'kex_exchange_identification:' in (d.get('agent_error') or ''):
  assert not (r/'chatdrug/run'/d['task']/'solution.smi').exists()
  ids.append(d['task'])
assert len(ids)==17
assert 'for attempt in range(6)' in (r/'transport_adapter.py').read_text()
locks=[]
for method in ['chatdrug','agentdrug']:
 f=(r/method/'batch.lock').open('a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
unaffected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for m in ['chatdrug','agentdrug'] for p in (r/m/'records').glob('*.json') if not (m=='chatdrug' and p.stem in ids)}
archive=r/'chatdrug/retry_archive'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());archive.mkdir(parents=True)
shutil.copy2(r/'parallel_status.json',archive/'parallel_status.before.json')
for tid in ids:
 for section in ['run','evaluator','logs','records']:
  suffix='.log' if section=='logs' else '.json' if section=='records' else ''
  source=r/'chatdrug'/section/(tid+suffix)
  if source.exists():
   assert source.resolve().is_relative_to((r/'chatdrug').resolve())
   target=archive/section/source.name;target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)
 assert tid not in state['blocked']['chatdrug']
(archive/'manifest.json').write_text(json.dumps({'tasks':sorted(ids),'reason':'user-authorized rerun of 17 SSH-handshake interrupted ChatDrug tasks','unaffected_record_hashes':unaffected},indent=2))
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in unaffected.items())
for p in ['experiment.exit','RESULTS.md']:
 src=r/'chatdrug'/p
 if src.exists():src.rename(archive/p)
state['state']='retry_requested';state['updated']=time.time()
tmp=r/'parallel_status.json.tmp';tmp.write_text(json.dumps(state,indent=2));tmp.replace(r/'parallel_status.json')
for f in locks:f.close()
subprocess.run(['systemctl','--user','start','smdd-type4-parallel.service'],check=True)
print('REQUEUED',len(ids),'ARCHIVE',archive)
print('UNRELATED_RECORDS_UNCHANGED',len(unaffected))
