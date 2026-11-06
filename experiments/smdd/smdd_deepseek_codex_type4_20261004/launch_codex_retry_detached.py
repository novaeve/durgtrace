from pathlib import Path
import json,subprocess,os,time,hashlib
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');batch=r/'codex_selected_retry_20261007'
manifest=json.loads((batch/'manifest.json').read_text())
assert not (batch/'detached_launch.json').exists()
assert not (batch/'status.json').exists()
assert all(hashlib.sha256((r/'runs/codex'/tid/'record.json').read_bytes()).hexdigest()==meta['record_sha256'] for tid,meta in manifest['tasks'].items())
python=Path('/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python')
with (batch/'driver.log').open('a') as log:
 proc=subprocess.Popen(['nohup',str(python),'-u',str(batch/'driver.py')],cwd=batch,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'))
time.sleep(3)
assert proc.poll() is None,(proc.returncode,(batch/'driver.log').read_text())
meta={'time':time.time(),'pid':proc.pid,'mode':'nohup with independent session','note':'User service daemon-reload returned 1 without diagnostics; no unit was started','task_count':3}
(batch/'detached_launch.json').write_text(json.dumps(meta,indent=2))
print('LAUNCHED',json.dumps(meta))
print('STATUS',(batch/'status.json').read_text() if (batch/'status.json').exists() else 'starting')
