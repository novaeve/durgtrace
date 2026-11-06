from pathlib import Path
import json,subprocess,os,time,hashlib,shutil
r=Path('/yimin/zlc/sol_pi_type4_20261004');d=json.loads((r/'repair_current.json').read_text());archive=Path(d['archive']);tid='smdd_004_ACE_4';out=r/'runs/solpi'/tid
assert json.loads((r/'repair_tests/result.json').read_text())['passed']
state=json.loads((out/'resume_state.json').read_text());assert state['submitted']
assert not (out/'result.json').exists() and not (out/'record.json').exists()
receipts=[json.loads(p.read_text()) for p in (out/'tools').glob('*.json')];accepted=next(t for t in receipts if t['name']=='submit' and t['result'].startswith('Submission accepted:'))
src=out/'workspace/solution.smi';assert src.stat().st_mtime<=accepted['ended']
shutil.copy2(src,out/'accepted_solution.smi');sha=hashlib.sha256(src.read_bytes()).hexdigest()
(out/'submission.json').write_text(json.dumps({'file_path':'solution.smi','sha256':sha,'accepted':accepted['ended'],'recovered_original_submission':True},indent=2))
(archive/'unaffected_records_sha256.json').write_text(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (r/'runs/solpi').glob('*/record.json')},indent=2))
env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONNOUSERSITE='1')
with (out/'scheduler_launch.log').open('a') as log:
 p=subprocess.Popen(['/yimin/zlc/molclaw_type4_20261003/rootfs/opt/conda/bin/python',str(r/'worker.py'),'solpi',tid,'--resume'],cwd=r,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
(archive/'accepted_worker.json').write_text(json.dumps({'task':tid,'pid':p.pid,'sha256':sha,'started':time.time()},indent=2));print('ORIGINAL_SUBMISSION_SCORING_STARTED',p.pid,sha)
