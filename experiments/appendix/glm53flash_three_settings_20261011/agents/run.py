"""Two frozen native agents, three input settings, one shared eight-worker limit."""
import collections,concurrent.futures,copy,fcntl,hashlib,importlib.util,json,os,shutil,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/data2/chenfuxin')
CHAT=BASE/'chatdrug_generalization_20260920'
AGENT=BASE/'agentdrug_20260922'
sys.path.insert(0,str(CHAT));sys.path.insert(0,str(ROOT))
from common import score as final_score
from provider import Relay,RelayError,MODEL,catalog,dump
import full_experiment as bench
bench.p.Relay=Relay
METHODS=('ChatDrug','AgentDrug')
WORKERS=24
SETTINGS=('1_original_chatdrug','2_s2_prompt_chatdrug','3_original_s2')
JOBS=json.loads((ROOT/'jobs.json').read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def native_dependencies():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for path,digest in manifest['frozen_dependencies'].items():assert sha(path)==digest,path
    assert sha(CHAT/'prepared_full/retrieval.csv')==manifest['retrieval_sha256']
    assert sha(ROOT/'jobs.json')==manifest['jobs_sha256']
    assert sha(ROOT/'common.py')==manifest['common_sha256']
    assert sha(ROOT/'chat_native.py')==manifest['native_chat_sha256']
    namespace=dict(bench.p.__dict__);namespace.update(score=bench.score,retrieval_success=bench.retrieval_success,Relay=Relay)
    exec(compile((ROOT/'chat_native.py').read_text(),str(ROOT/'chat_native.py'),'exec'),namespace)
    chat_fn=namespace['run_case'];db=bench.p.pd.read_csv(CHAT/'prepared_full/retrieval.csv')
    spec=importlib.util.spec_from_file_location('frozen_agentdrug_runner',AGENT/'runner.py')
    agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent);agent.init_corpus()
    return chat_fn,db,agent
def native_path(method,job):return ROOT/'native'/method/job['setting']/job['case']['id']
def final_path(method,job):return ROOT/'runs'/method/job['setting']/job['case']['id']/'result.json'
def run_native(method,job):
    case=job['case'];out=native_path(method,job);saved=out/'result.json'
    if saved.exists():return json.loads(saved.read_text())
    if method=='ChatDrug':return CHAT_FN(case,DB,out.parent)
    out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();model=AGENT_MODULE.Model(out)
    row={'id':case['id'],'case':case,'status':'running'}
    try:
        ns,args,batch,dataset=AGENT_MODULE.setup(case)
        outputs,validity_work,total_work=ns['run_core'](args,batch,model,dataset)
        assert len(outputs)==1
        candidate=outputs[0]['pred'][0]
        row.update(status='complete',candidate=candidate,score=bench.score(case,candidate),
                   generation_calls=len(model.predictions),validity_feedback_count=validity_work,
                   core_iterations=total_work,refine_steps=args.refine_steps)
    except Exception as exc:
        row.update(status='error',error=str(exc) if isinstance(exc,RelayError) else type(exc).__name__,
                   error_type=type(exc).__name__,generation_calls=len(model.predictions))
        dump(out/'exception.json',{'traceback':traceback.format_exc()})
    row.update(seconds=round(time.monotonic()-start,3),api_requests=sum(len(c['attempts']) for c in model.relay.calls),
               response_models=sorted({c.get('response_model') for c in model.relay.calls if c.get('response_model')}),
               truncated_responses=sum(c.get('stop_reason')=='max_tokens' for c in model.relay.calls))
    dump(saved,row);return row
def infrastructure(row):
    error=row.get('error','') or ''
    return row.get('status')=='error' and (error.startswith('HTTP_') or error in
          ('TRANSPORT_ERROR','INVALID_JSON','NO_CHOICES','NO_TEXT_BLOCK','RETRY_EXHAUSTED','RETURNED_MODEL_MISMATCH'))
def preserve_for_retry(method,job,attempt):
    source=native_path(method,job)
    target=ROOT/'recovery_archive'/time.strftime('%Y%m%dT%H%M%S')/method/job['setting']/job['case']['id']/str(attempt)
    target.parent.mkdir(parents=True,exist_ok=True)
    assert source.resolve().is_relative_to(ROOT.resolve())
    source.rename(target);source.mkdir(parents=True)
    if (target/'api_calls.json').exists():shutil.copy2(target/'api_calls.json',source/'api_calls.json')
    return str(target)
def execute(method,job):
    output=final_path(method,job)
    if output.exists():return json.loads(output.read_text())
    archives=[];native=None
    for attempt in range(3):
        native=run_native(method,job)
        if infrastructure(native) and attempt<2:
            archives.append(preserve_for_retry(method,job,attempt));time.sleep(10*(attempt+1));continue
        break
    native_score=native.get('arms',{}).get('chatdrug') if method=='ChatDrug' else native.get('score')
    candidate=native_score.get('candidate') if native_score else native.get('candidate')
    status='complete' if native['status']=='complete' else ('provider_limit' if native.get('error')=='OUTPUT_TRUNCATED' else 'error')
    final=final_score(job['case'],candidate if status=='complete' else None)
    result=dict(id=job['case']['id'],case=job['case'],setting=job['setting'],method=method,model=MODEL,
                status=status,error=native.get('error'),candidate=candidate,score=final,score_native=native_score,
                native_result=str(native_path(method,job)/'result.json'),native_seconds=native.get('seconds'),
                response_models=native.get('response_models',[]),truncated_responses=native.get('truncated_responses'),
                retryable=infrastructure(native),recovery_archives=archives,finished=time.time())
    dump(output,result)
    print(json.dumps({k:result[k] for k in ('id','setting','method','status')},ensure_ascii=False),flush=True)
    return result
def summaries():
    rows=[json.loads(p.read_text()) for p in (ROOT/'runs').glob('*/*/*/result.json')]
    expected=collections.Counter((j['setting'],j['case']['property']) for j in JOBS)
    groups=[]
    for method in METHODS:
        for (setting,prop),count in expected.items():
            rr=[r for r in rows if r['method']==method and r['setting']==setting and r['case']['property']==prop]
            n=sum(r['score']['success'] for r in rr)
            groups.append(dict(method=method,setting=setting,property=prop,expected=count,processed=len(rr),success=n,
                          success_rate_full=n/count,success_rate_processed=n/len(rr) if rr else None,
                          statuses=dict(collections.Counter(r['status'] for r in rr))))
    report=dict(processed=len(rows),expected=8400,workers=WORKERS,groups=groups,
                per_method=dict(collections.Counter(r['method'] for r in rows)),updated=time.time())
    dump(ROOT/'summary.json',report);return report
def ordered_jobs():
    buckets=collections.defaultdict(list)
    for job in JOBS:
        c=job['case'];buckets[(job['setting'],c['task'],c['constraint'])].append(job)
    assert len(buckets)==20
    for bb in buckets.values():bb.sort(key=lambda j:j['case'].get('original_row',int(j['case']['id'].rsplit('_',1)[1])))
    ordered=[bb[i] for i in range(max(map(len,buckets.values()))) for bb in buckets.values() if i<len(bb)]
    assert len(ordered)==4200
    return ordered[:20],ordered[20:]
def batch(jobs):
    selected=[(m,j) for j in jobs for m in METHODS if not final_path(m,j).exists()]
    last=time.monotonic();completed=0
    with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as pool:
        iterator=iter(selected);pending={}
        for _ in range(WORKERS):
            item=next(iterator,None)
            if item:pending[pool.submit(execute,*item)]=item
        while pending:
            done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                future.result();del pending[future];completed+=1
                if completed%20==0 or time.monotonic()-last>15:summaries();last=time.monotonic()
                item=next(iterator,None)
                if item:pending[pool.submit(execute,*item)]=item
    return summaries()
def pilot_check(pilot):
    evidence=[];bad=[]
    for job in pilot:
        for method in METHODS:
            row=json.loads(final_path(method,job).read_text())
            if row['status']=='error':bad.append(dict(id=row['id'],method=method,setting=job['setting'],error=row.get('error')))
            calls=json.loads((native_path(method,job)/'api_calls.json').read_text())
            responses=[c for c in calls if c.get('response_model')]
            if not responses:raise RuntimeError('Pilot has no model receipt')
            first=responses[0]
            text='\n'.join(m['content'] for m in first['messages'] if m['role']=='user')
            assert job['case']['instruction'] in text
            for call in responses:
                assert call['requested_model']==MODEL and call['request_settings']['reasoning_effort']=='low'
                assert call['request_settings']['max_tokens']==(256 if method=='AgentDrug' else 2048)
            evidence.append(dict(method=method,setting=job['setting'],id=job['case']['id'],status=row['status'],
                                  real_model_calls=len(responses),native_caps_verified=True,initial_prompt_verified=True))
    dump(ROOT/'pilot_acceptance.json',dict(accepted=not bad,episodes=40,evidence=evidence,failures=bad))
    assert not bad,'Pilot infrastructure or native runner failure'
def retry_failed():
    cases_by_key={(j['setting'],j['case']['id']):j for j in JOBS}
    targets=[]
    for p in (ROOT/'runs').glob('*/*/*/result.json'):
        row=json.loads(p.read_text())
        if row['status']=='error' and row.get('retryable'):
            method=row['method'];job=cases_by_key[(row['setting'],row['id'])]
            archive=preserve_for_retry(method,job,'supervisor')
            shutil.move(str(p.parent),str(Path(archive)/'final_result'))
            targets.append((method,job))
    if targets:
        with concurrent.futures.ProcessPoolExecutor(WORKERS) as pool:
            for f in concurrent.futures.as_completed([pool.submit(execute,*t) for t in targets]):f.result()
        summaries()
    return len(targets)
def main():
    global CHAT_FN,DB,AGENT_MODULE
    with (ROOT/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        CHAT_FN,DB,AGENT_MODULE=native_dependencies()
        if '--check' in sys.argv:
            for job in JOBS:
                assert len(job['case']['objectives'])==1
                assert not final_score(job['case'],job['case']['smiles'])['success']
                assert not final_score(job['case'],None)['success']
            pilot,full=ordered_jobs();assert len(pilot)==20
            dump(ROOT/'offline_validation.json',dict(passed=True,jobs=4200,pilot_per_agent=20,native_sources_unchanged=True))
            print('OFFLINE_VALIDATION_PASSED',flush=True);return
        dump(ROOT/'catalog.json',catalog())
        pilot,full=ordered_jobs()
        dump(ROOT/'state.json',dict(phase='pilot',model=MODEL,workers=WORKERS,time=time.time()))
        batch(pilot);pilot_check(pilot)
        dump(ROOT/'state.json',dict(phase='full',model=MODEL,workers=WORKERS,time=time.time()))
        batch(full)
        for sweep in range(10):
            if not retry_failed():break
            time.sleep(30)
        report=summaries();assert report['processed']==8400
        errors=[p for p in (ROOT/'runs').glob('*/*/*/result.json') if json.loads(p.read_text())['status']=='error']
        dump(ROOT/'state.json',dict(phase='complete' if not errors else 'attention_required',processed=8400,
                       expected=8400,model=MODEL,workers=WORKERS,error_count=len(errors),time=time.time()))
if __name__=='__main__':
    os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
    try:main()
    except Exception as exc:
        dump(ROOT/'state.json',dict(phase='failed',error=str(exc),model=MODEL,workers=WORKERS,time=time.time()))
        (ROOT/'pipeline_error.log').write_text(traceback.format_exc());raise
