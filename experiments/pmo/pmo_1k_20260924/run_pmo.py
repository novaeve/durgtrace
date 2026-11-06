import argparse, collections, concurrent.futures, fcntl, json, os, pathlib, random, subprocess, sys, time, traceback, warnings
os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pmo_common import ROOT, MODEL, SEEDS, Ledger, Relay, BudgetExhausted, LongTruncation, dump, sha, canonical, make_oracle
from task_specs import TASKS
from adapters import METHODS
warnings.filterwarnings('ignore')

def job(method,task,seed,stage,budget):
    from tdc import Oracle
    for path,digest in json.loads((ROOT/'prepared/dependencies.json').read_text()).items():
        assert sha(path)==digest, 'Dependency changed: '+path
    out=ROOT/'runs'/stage/method/task/str(seed);out.mkdir(parents=True,exist_ok=True)
    lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (out/'result.json').exists() and json.loads((out/'result.json').read_text())['status'] in ['complete','skipped_long_truncation']:return
    config={'method':method,'task':task,'seed':seed,'stage':stage,'budget':budget,'model':MODEL,
            'initial_size':100,'parent_pool':100,'history_size':20,'temperature':0,
            'runtime_policy':'20260925_seed0_no_stagnation_stop_3_provider_truncations_round_robin',
            'dependencies_manifest':sha(ROOT/'prepared/dependencies.json'),
            'source_hashes':{n:sha(ROOT/n) for n in ['run_pmo.py','pmo_common.py','adapters.py','task_specs.py']}}
    if (out/'config.json').exists():
        previous=json.loads((out/'config.json').read_text())
        permitted={'source_hashes','runtime_policy'}
        assert {k:v for k,v in previous.items() if k not in permitted}=={k:v for k,v in config.items() if k not in permitted}
        if previous!=config:dump(out/'config_history'/(sha(out/'config.json')+'.json'),previous)
    dump(out/'config.json',config)
    if (out/'result.json').exists():
        dump(out/'result_history'/(str(time.time_ns())+'.json'),json.loads((out/'result.json').read_text()))
        (out/'result.json').unlink()
    start=time.time();ledger=None;relay=Relay(out)
    state=json.loads((out/'state.json').read_text()) if (out/'state.json').exists() else {'episode':0,'no_progress':0}
    try:
        ledger=Ledger(out,make_oracle(TASKS[task][0]),budget)
        initialization=json.loads((ROOT/'prepared/initial.json').read_text())[str(seed)]
        for sm in initialization:ledger.score(sm,'initialization')
        slice_start=state['episode']
        while len(ledger.buffer)<budget:
            if len(relay.long_truncations)>=3:
                status='skipped_long_truncation';break
            # Scheduling quantum only: unfinished searches are requeued, never abandoned.
            if stage=='full' and state['episode']-slice_start>=100:
                dump(out/'progress.json',{'status':'queued','episode':state['episode'],'time':time.time(),**ledger.metrics()})
                return 'yielded'
            i=state['episode']
            if 'parent' not in state:
                pool=sorted(ledger.rows,key=lambda r:(-r['score'],r['index']))[:100]
                state['parent']=random.Random(seed*1000003+i).choice(pool)['smiles']
                state['boundary']=len(ledger.rows);dump(out/'state.json',state)
            ledger.episode_boundary=state['boundary']
            dump(out/'progress.json',{'status':'running','episode':i,'time':time.time(),**ledger.metrics()})
            try:
                trace=METHODS[method](task,state['parent'],ledger,relay,f'episode/{i}',out)
            except BudgetExhausted:
                trace={'budget_exhausted':True}
            except LongTruncation:
                trace={'unscored_provider_truncation':True,'count':len(relay.long_truncations)}
            dump(out/'episodes'/f'{i:06d}.json',{'parent':state['parent'],'before':state['boundary'],'after':len(ledger.rows),'trace':trace})
            state={'episode':i+1,'no_progress':state['no_progress']+1 if len(ledger.rows)==state['boundary'] else 0}
            dump(out/'state.json',state)
        else:status='complete'
        dump(out/'result.json',{'status':status,'time':time.time(),'seconds_this_process':time.time()-start,
                                **ledger.metrics(),**relay.usage(),'episodes':state['episode'],
                                'long_truncations':len(relay.long_truncations)})
        print(json.dumps({'method':method,'task':task,'seed':seed,'status':status,'calls':len(ledger.rows)}),flush=True)
    except Exception as e:
        dump(out/'result.json',{'status':'error','error_type':type(e).__name__,'error':str(e)[:500],
            'traceback':traceback.format_exc(),'time':time.time(),**(ledger.metrics() if ledger else {}),**relay.usage()})
        raise

def summarize(stage):
    rows=[]
    for p in (ROOT/'runs'/stage).glob('*/*/*/config.json'):
        c=json.loads(p.read_text());out=p.parent
        r=json.loads((out/'result.json').read_text()) if (out/'result.json').exists() else (
            json.loads((out/'progress.json').read_text()) if (out/'progress.json').exists() else {'status':'starting'})
        rows.append({k:c[k] for k in ['method','task','seed']}|r)
    status={}
    for row in rows:status[row['status']]=status.get(row['status'],0)+1
    result={'time':time.time(),'stage':stage,'status_counts':status,'oracle_calls':sum(r.get('oracle_calls',0) for r in rows),'jobs':rows}
    dump(ROOT/'runs'/stage/'summary.json',result);return result

def suite(stage):
    root=ROOT/'runs'/stage;root.mkdir(parents=True,exist_ok=True)
    lock=(root/'suite.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    tasks=['qed','drd2','amlodipine_mpo'] if stage=='pilot' else list(TASKS)
    seeds=[0] if stage=='pilot' else SEEDS
    budget=110 if stage=='pilot' else 1000
    if stage=='full':
        pilot=summarize('pilot');assert len(pilot['jobs'])==12 and pilot['status_counts']=={'complete':12},pilot['status_counts']
    jobs=[(m,t,s) for s in seeds for t in tasks for m in METHODS]
    dump(root/'manifest.json',{'expected':len(jobs),'methods':list(METHODS),'tasks':tasks,'seeds':seeds,'budget':budget,'workers':4})
    def launch(spec):
        m,t,s=spec;out=root/m/t/str(s);out.mkdir(parents=True,exist_ok=True)
        cmd=[sys.executable,str(ROOT/'run_pmo.py'),'job','--method',m,'--task',t,'--seed',str(s),'--stage',stage,'--budget',str(budget)]
        with (out/'process.log').open('a') as f:
            result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
        return {'method':m,'task':t,'seed':s,'exit':result.returncode}
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        # Bounded queue; do not launch hundreds of failing API jobs on a systemic error.
        pending=collections.deque(jobs);active={}
        for _ in range(4):
            spec=pending.popleft() if pending else None
            if spec:active[pool.submit(launch,spec)]=spec
        while active:
            done,_=concurrent.futures.wait(active,return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                spec=active.pop(f);r=f.result();print(json.dumps(r),flush=True);summary=summarize(stage)
                if r['exit']==75:pending.append(spec)
                elif r['exit']!=0:failures.append(r)
                if len(failures)>=3:continue
                spec=pending.popleft() if pending else None
                if spec:active[pool.submit(launch,spec)]=spec
    summary=summarize(stage)
    terminal=sum(summary['status_counts'].get(k,0) for k in ['complete','skipped_long_truncation'])
    if failures or terminal!=len(jobs):raise SystemExit(2)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['pilot','full','job','status']);ap.add_argument('--method',choices=METHODS);ap.add_argument('--task',choices=TASKS);ap.add_argument('--seed',type=int,default=0);ap.add_argument('--stage',default='pilot');ap.add_argument('--budget',type=int,default=1000);a=ap.parse_args()
    if a.action=='job':
        if job(a.method,a.task,a.seed,a.stage,a.budget)=='yielded':raise SystemExit(75)
    elif a.action=='status':print(json.dumps(summarize(a.stage),ensure_ascii=False))
    else:suite(a.action)
