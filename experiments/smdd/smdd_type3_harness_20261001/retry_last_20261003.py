from pathlib import Path
import os,sys,json,time,inspect,fcntl,shutil,subprocess,traceback,hashlib
ROOT=Path(__file__).resolve().parent
BASE=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')
sys.path.insert(0,str(BASE))
import runtime
import evaluate as evaluator
from runtime import dump
RETRY=ROOT/'reassessment_last_20261003';RETRY.mkdir(exist_ok=True)
CASES=[('codex','smdd_003_6ME6_0')]

def summary():
    data={}
    for method in ['molclaw','codex']:
        rows=[json.loads(p.read_text()) for p in (ROOT/'evaluation'/method).glob('*/result.json')]
        data[method]={'expected':52,'evaluated':len(rows),**{s:sum(x['status']==s for x in rows) for s in ['passed','failed','errored']}}
    dump(ROOT/'evaluation/summary.json',data)

def work():
    with (ROOT/'score.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from idle_gpu_retry import gpu_run
        ns={'gpu_run':gpu_run}
        source=inspect.getsource(evaluator.evaluate)
        assert "ev=ROOT/'evaluation'/method/tid" in source
        source=source.replace("ev=ROOT/'evaluation'/method/tid","ev=ROOT/'reassessment_last_20261003'/method/tid")
        ens=dict(evaluator.__dict__,ROOT=ROOT,gpu_run=ns['gpu_run']);exec(compile(source,'<independent-retry>','exec'),ens)
        hashes={m+'/'+t:hashlib.sha256((ROOT/'runs'/m/t/'solution.smi').read_bytes()).hexdigest() for m,t in CASES}
        dump(RETRY/'manifest.json',{'cases':CASES,'gpu':os.environ['SMDD_TYPE3_GPU'],'required_free_mib':31500,'allocator':'expandable_segments:True','max_parallel_samples':1,'diffusion_samples':10,'diffusion_samples_affinity':10,'seed':42,'thresholds':'unchanged','solution_sha256':hashes})
        rows=[]
        for method,tid in CASES:
            original=ROOT/'evaluation'/method/tid/'result.json';saved=RETRY/'original'/method/tid/'result.json'
            if not saved.exists():
                raw=json.loads(original.read_text());assert raw['status']=='errored';dump(saved,raw)
            dump(RETRY/'progress.json',{'status':'running','current':method+'/'+tid,'completed':len(rows),'expected':1,'results':rows})
            try:
                if shutil.disk_usage(ROOT).free<10*1024**3:raise RuntimeError('Free disk below 10 GiB')
                result=ens['evaluate'](tid,method)
                assert hashlib.sha256((ROOT/'runs'/method/tid/'solution.smi').read_bytes()).hexdigest()==hashes[method+'/'+tid]
                if result['status']!='errored':
                    result['reassessment']={'raw_result':str(saved),'retry_directory':str(RETRY/method/tid),'time':time.time(),'gpu':os.environ['SMDD_TYPE3_GPU']}
                    dump(original,result)
                row={'method':method,'task':tid,'status':result['status']}
            except Exception as exc:
                row={'method':method,'task':tid,'status':'errored','error':str(exc)}
                dump(RETRY/method/tid/'worker_error.json',{'traceback':traceback.format_exc()})
            rows.append(row);summary();print(json.dumps(row),flush=True)
        dump(RETRY/'progress.json',{'status':'complete' if all(r['status']!='errored' for r in rows) else 'needs_attention','completed':1,'expected':1,'results':rows})

if __name__=='__main__':
    if '--work' in sys.argv:work()
    else:
        pidfile=RETRY/'worker.pid'
        if pidfile.exists():
            stat=Path('/proc')/pidfile.read_text().strip()/'stat'
            if stat.exists() and stat.read_text().split()[2]!='Z':raise RuntimeError('Retry already running')
        env=dict(os.environ,SMDD_TYPE3_GPU='auto-idle',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        with (RETRY/'worker.log').open('a') as log:
            proc=subprocess.Popen([sys.executable,__file__,'--work'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        pidfile.write_text(str(proc.pid));time.sleep(3)
        assert proc.poll() is None,(RETRY/'worker.log').read_text()[-1500:]
        print(json.dumps({'pid':proc.pid,'progress':json.loads((RETRY/'progress.json').read_text())}))
