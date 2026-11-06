"""Score the nine frozen MolClaw submissions, preserve originals, publish terminal scores."""
from pathlib import Path
import collections, concurrent.futures, fcntl, hashlib, json, os, shutil, subprocess, sys, time, traceback

BASE=Path('/yimin/zlc/molclaw_type4_20261003')
BATCH=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import evaluate as evaluator
import runtime
from gpu_slots import acquire

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
    Path(out).mkdir(parents=True,exist_ok=True)
    with acquire(Path(log_path).parent) as gpu:
        argv=[str(runtime.BOLTZ),str(BATCH/'boltz_transport.py'),'predict',str(yaml_path),
              '--out_dir',str(out),'--cache',str(BASE/'boltz_cache'),'--use_msa_server',
              '--use_potentials','--diffusion_samples',str(samples),'--seed',str(seed),
              '--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),PYTHONNOUSERSITE='1',
                 LD_LIBRARY_PATH=str(runtime.ROOTFS/'opt/conda/lib'),OMP_NUM_THREADS='2',
                 OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
        runtime.dump(Path(log_path).parent/'boltz_provenance.json',{
            'argv':argv,'gpu':gpu,'seed':seed,'samples':samples,'source':'official Boltz with process-local network timeout',
            'transport_sha256':sha(BATCH/'boltz_transport.py')})
        with open(log_path,'w') as log:
            process=subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        predictions=list(Path(out).rglob('affinity_agent_dock.json'))
        if process.returncode or not predictions:
            raise RuntimeError('Boltz produced no usable affinity result; inspect preserved boltz.log')
        return process.returncode

def worker(tid,manifest):
    state_path=BATCH/'workers'/f'{tid}.json'
    if state_path.exists():
        previous=json.loads(state_path.read_text())
        if previous.get('published'):
            assert sha(BASE/'runs/molclaw'/tid/'solution.smi')==manifest['tasks'][tid]['submission_sha256']
            assert json.loads((BASE/'evaluation/molclaw'/tid/'rescore_provenance.json').read_text())['batch']==str(BATCH)
            return previous['score_status']
    runtime.dump(state_path,{'task':tid,'status':'running','started':time.time()})
    try:
        frozen=BATCH/'runs/molclaw'/tid/'solution.smi'
        source=BASE/'runs/molclaw'/tid/'solution.smi'
        assert sha(frozen)==sha(source)==manifest['tasks'][tid]['submission_sha256']
        result=evaluator.evaluate(tid,'molclaw')
        if result['status'] in ('passed','failed'):
            canonical=BASE/'evaluation/molclaw'/tid
            assert sha(canonical/'result.json')==manifest['tasks'][tid]['original_result_sha256']
            assert sha(source)==manifest['tasks'][tid]['submission_sha256']
            staged=canonical.parent/(tid+'.rescore_'+BATCH.name)
            assert not staged.exists()
            shutil.copytree(BATCH/'evaluation/molclaw'/tid,staged)
            canonical.rename(BATCH/'original_evaluation'/tid)
            try:staged.rename(canonical)
            except Exception:
                (BATCH/'original_evaluation'/tid).rename(canonical)
                raise
            runtime.dump(canonical/'rescore_provenance.json',{'batch':str(BATCH),'original_evaluation':str(BATCH/'original_evaluation'/tid),
                'submission_sha256':sha(source),'score_status':result['status'],'promoted':time.time()})
        runtime.dump(state_path,{'task':tid,'status':'finished','score_status':result['status'],'published':result['status'] in ('passed','failed'),'ended':time.time()})
        print(json.dumps({'task':tid,'score_status':result['status'],'published':result['status'] in ('passed','failed')}),flush=True)
        return result['status']
    except Exception as exc:
        runtime.dump(state_path,{'task':tid,'status':'infrastructure_error','error':repr(exc),'traceback':traceback.format_exc(),'ended':time.time()})
        print(json.dumps({'task':tid,'error':repr(exc)}),flush=True)
        return 'errored'

def snapshot(ids):
    states={tid:json.loads((BATCH/'workers'/f'{tid}.json').read_text()) for tid in ids if (BATCH/'workers'/f'{tid}.json').exists()}
    runtime.dump(BATCH/'status.json',{'total':len(ids),'time':time.time(),'states':states,
        'running':sum(d['status']=='running' for d in states.values()),
        'ended':sum(d['status']!='running' for d in states.values()),'waiting':len(ids)-len(states)})

def main():
    lock=(BATCH/'driver.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifest=json.loads((BATCH/'manifest.json').read_text());ids=list(manifest['tasks'])
    assert len(ids)==9
    evaluator.ROOT=BATCH
    evaluator.gpu_run=gpu_run
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,tid,manifest) for tid in ids]
        while not all(f.done() for f in futures):
            snapshot(ids);time.sleep(5)
        results=[f.result() for f in futures]
    snapshot(ids)
    runtime.dump(BATCH/'completion.json',{'time':time.time(),'results':dict(collections.Counter(results)),
        'submission_hashes_unchanged':all(sha(BASE/'runs/molclaw'/tid/'solution.smi')==manifest['tasks'][tid]['submission_sha256'] for tid in ids)})
    # The original MolClaw scheduler has ended; refresh only its result summary.
    if subprocess.getoutput('systemctl --user is-active molclaw-type4-a100.service').strip()=='inactive':
        status=json.loads((BASE/'status.json').read_text())
        status.update(time=time.time(),blocked=[p.parent.name for p in (BASE/'evaluation/molclaw').glob('*/result.json') if json.loads(p.read_text()).get('status')=='errored'],rescore_batch=str(BATCH))
        runtime.dump(BASE/'status.json',status)
    print('RESCORE_BATCH_COMPLETE',json.dumps(dict(collections.Counter(results))),flush=True)

if __name__=='__main__':main()
