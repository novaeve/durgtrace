"""Reassess the fixed submission using the existing near-empty-GPU evaluator."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path('/data2/chenfuxin/liddia_smdd_type3_20261004')
SOURCE=ROOT/'source'
TASK='smdd_003_6ME6_0'
ORIGINAL=ROOT/'runs/full_high_v1'/TASK
RETRY=ROOT/'reassessment_20261005'/TASK
sys.path.insert(0,str(SOURCE))
from runtime_safety import atomic_json
import evaluate_liddia_type3 as evaluator
sys.path.insert(0,'/data2/chenfuxin/smdd_type3_harness_20261001')
from idle_gpu_retry import gpu_run

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def payload_on_idle_gpu(payload,output,gpu=0,samples=10,seed=42,job_name='input'):
    import yaml
    assert samples==10 and seed==42
    if Path(job_name).name!=job_name or job_name in ('','.','..'):raise ValueError('Invalid prediction job name')
    job=Path(output)/('boltz_'+uuid.uuid4().hex[:12]);job.mkdir(parents=True)
    path=job/(job_name+'.yaml');path.write_text(yaml.safe_dump(payload))
    rc=gpu_run(path,job/'out',job/'boltz.log',samples=samples,seed=seed)
    if rc:raise RuntimeError('Boltz failed; original diagnostics preserved at '+str(job/'boltz.log'))
    prediction=job/'out'/('boltz_results_'+job_name)/'predictions'/job_name
    value=json.loads((prediction/('affinity_'+job_name+'.json')).read_text())
    structures=list(prediction.glob(job_name+'_model_*.cif'))
    assert len(structures)==10, 'Expected unchanged 10 structure samples'
    value['prediction_directory']=str(job/'out')
    return value

def work():
    with (ROOT/'reassessment.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        RETRY.mkdir(parents=True,exist_ok=False)
        original_result=ORIGINAL/'evaluation/result.json'
        old=json.loads(original_result.read_text());assert old['status']=='errored',old['status']
        saved=RETRY/'original';saved.mkdir()
        shutil.copy2(original_result,saved/'evaluation_result.json')
        batch=ROOT/'runs/full_high_v1/batch_status.json'
        shutil.copy2(batch,saved/'batch_status.json')
        protected={name:sha(ORIGINAL/name) for name in ('solution.smi','agent_result.json','budget.jsonl','llm_calls.json')}
        shutil.copy2(ORIGINAL/'solution.smi',RETRY/'solution.smi')
        atomic_json(RETRY/'manifest.json',{'task':TASK,'source':str(ORIGINAL),'submission_sha256':protected['solution.smi'],
            'protected_generation_hashes':protected,'required_free_mib':31500,'gpu_selection':'shared lock + near-empty GPU',
            'allocator':'expandable_segments:True','diffusion_samples':10,'affinity_samples':10,'max_parallel_samples':1,
            'seed':42,'thresholds':'unchanged','agent_rerun':False,'started':time.time(),
            'retry_script_sha256':sha(Path(__file__)),'idle_gpu_transport_sha256':sha(Path('/data2/chenfuxin/smdd_type3_harness_20261001/idle_gpu_retry.py'))})
        atomic_json(RETRY/'progress.json',{'state':'running','task':TASK,'pid':os.getpid(),'started':time.time()})
        try:
            if shutil.disk_usage(ROOT).free<10*1024**3:raise RuntimeError('Free disk below 10 GiB')
            evaluator.boltz_payload=payload_on_idle_gpu
            result=evaluator.evaluate(TASK,RETRY,0)
            assert all(sha(ORIGINAL/name)==digest for name,digest in protected.items()),'Original generation changed'
            assert sha(RETRY/'solution.smi')==protected['solution.smi']
            if result['status'] in ('passed','failed'):
                result['reassessment']={'original_result':str(saved/'evaluation_result.json'),'retry_directory':str(RETRY),
                                        'time':time.time(),'submission_unchanged':True,'required_free_mib':31500}
                atomic_json(original_result,result)
                state=json.loads(batch.read_text())
                entry=state['finished'][TASK]
                entry.update(evaluation_status=result['status'],evaluation_exit=0,reassessment=str(RETRY),reassessed=time.time())
                state['workers']['5']={'gpu':5,'phase':'complete'}
                if len(state['finished'])==52 and all(x.get('evaluation_status') in ('passed','failed') for x in state['finished'].values()):
                    state['state']='complete'
                state.update(updated=time.time())
                atomic_json(batch,state)
                summary={'total':52,'submitted':52,**{s:sum(x.get('evaluation_status')==s for x in state['finished'].values()) for s in ('passed','failed','errored')}}
                atomic_json(ROOT/'result_summary.json',summary)
                atomic_json(RETRY/'progress.json',{'state':'complete','task':TASK,'status':result['status'],'ended':time.time(),'summary':summary})
            else:
                atomic_json(RETRY/'progress.json',{'state':'needs_attention','task':TASK,'status':result['status'],'ended':time.time()})
            print(json.dumps({'task':TASK,'status':result['status'],'metrics':[{k:s.get(k) for k in ('name','status','result')} for s in result.get('steps',[])]}),flush=True)
        except Exception:
            atomic_json(RETRY/'progress.json',{'state':'needs_attention','task':TASK,'error':traceback.format_exc(),'ended':time.time()})
            raise

if __name__=='__main__':
    if '--work' in sys.argv:work()
    else:
        assert not RETRY.exists(),'Existing retry must be inspected before another attempt'
        with (ROOT/'reassessment_20261005.log').open('a') as log:
            env=dict(os.environ,PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
            proc=subprocess.Popen([sys.executable,__file__,'--work'],cwd=SOURCE,env=env,stdin=subprocess.DEVNULL,
                                  stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (ROOT/'reassessment_20261005.pid').write_text(str(proc.pid))
        print(json.dumps({'pid':proc.pid,'retry':str(RETRY)}))
