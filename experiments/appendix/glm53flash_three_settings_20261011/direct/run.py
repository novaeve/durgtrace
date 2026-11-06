"""Independent one-response model baseline; no agent, tools, feedback or selection."""
import collections, concurrent.futures, errno, fcntl, hashlib, json, os, sys, time
import urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from common import dump, score
MODEL='glm-5.3-flash'
WORKERS=16
URL='http://127.0.0.1:18853/v4/chat/completions'
OUTPUT_RULE='\n\nReturn exactly one final molecule as a SMILES string and nothing else. Do not give explanations or alternative molecules.'

def request_body(case):
    return {'model':MODEL,'messages':[{'role':'user','content':case['instruction']+OUTPUT_RULE}],
            'temperature':0,'reasoning_effort':'low','max_tokens':2048,'n':1,'stream':False}

def parse_single(content):
    # Only trim surrounding whitespace; never extract, repair or choose molecules.
    if not isinstance(content,str):return None
    candidate=content.strip()
    return candidate if candidate and not any(c.isspace() for c in candidate) and '`' not in candidate else None

def run_one(job):
    case=job['case'];directory=ROOT/'runs/GLM_direct'/job['setting']/case['id']
    result_path=directory/'result.json';receipt_path=directory/'api.json'
    if result_path.exists():return json.loads(result_path.read_text())
    body=request_body(case)
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_text())
        assert receipt['request']==body and receipt['origin']=='independent_official_api'
    else:
        for previous in directory.glob('transport_error_*.json'):
            if 'Connection refused' not in json.loads(previous.read_text()).get('error',''):
                raise RuntimeError('AMBIGUOUS_TRANSPORT: earlier request needs inspection')
        for attempt in range(8):
            if (ROOT.parent/'provider_hold.json').exists():raise RuntimeError('PROVIDER_HOLD')
            started=time.time()
            request=urllib.request.Request(URL,data=json.dumps(body).encode(),
                headers={'Content-Type':'application/json','Authorization':'Bearer local-experiment'})
            try:
                with urllib.request.urlopen(request,timeout=900) as response:
                    data=json.load(response)
                assert data.get('model')==MODEL,'Unexpected provider model'
                assert len(data.get('choices',[]))==1,'Expected exactly one response'
                receipt={'origin':'independent_official_api','request':body,'response':data,
                         'started':started,'received':time.time(),'transport_attempt':attempt+1}
                dump(receipt_path,receipt)
                break
            except urllib.error.HTTPError as error:
                detail=error.read().decode('utf-8','replace')
                dump(directory/('http_error_'+str(attempt+1)+'.json'),
                     {'status':error.code,'body':detail,'started':started,'time':time.time()})
                if any(code in detail for code in ('1113','EXPERIMENT_HALTED')):
                    raise RuntimeError('PROVIDER_HOLD')
                if error.code not in (429,500,502,503,504):raise
                if attempt==7:raise
                time.sleep(min(30,2**(attempt+1)))
            except (urllib.error.URLError,TimeoutError,ConnectionError) as error:
                not_sent=isinstance(error,urllib.error.URLError) and getattr(error.reason,'errno',None)==errno.ECONNREFUSED
                dump(directory/('transport_error_'+str(attempt+1)+'.json'),
                     {'error':str(error),'started':started,'time':time.time(),
                      'outcome_unknown':not not_sent})
                if not_sent and attempt<7:
                    time.sleep(min(30,2**(attempt+1)))
                    continue
                # Never repeat an ambiguous request: it may already have generated an answer.
                raise RuntimeError('AMBIGUOUS_TRANSPORT: inspect before resuming') from error
        else:raise RuntimeError('No response')
    answer=receipt['response']['choices'][0]
    content=answer.get('message',{}).get('content')
    finish=answer.get('finish_reason')
    candidate=parse_single(content)
    status='provider_limit' if finish in ('length','max_tokens') else 'complete'
    evaluated=candidate if status=='complete' else None
    row={'id':case['id'],'case':case,'setting':job['setting'],'method':'GLM_direct','model':MODEL,
         'status':status,'candidate':candidate,'score':score(case,evaluated),'output':content,
         'logical_model_calls':1,'origin':'independent_official_api',
         'request_id':receipt['response'].get('id'),'finish_reason':finish,
         'receipt_sha256':hashlib.sha256(receipt_path.read_bytes()).hexdigest(),'finished':time.time()}
    dump(result_path,row)
    return row

def main():
    with (ROOT/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        jobs=json.loads((ROOT/'jobs.json').read_text());assert len(jobs)==4200
        manifest=json.loads((ROOT/'manifest.json').read_text())
        assert manifest['generation']=='independent_single_response_no_harness'
        assert hashlib.sha256((ROOT/'jobs.json').read_bytes()).hexdigest()==manifest['jobs_sha256']
        rows={}
        for file in (ROOT/'runs/GLM_direct').glob('*/*/result.json'):
            row=json.loads(file.read_text());assert row['origin']=='independent_official_api'
            rows[(row['setting'],row['id'])]=row
        expected=collections.Counter((j['setting'],j['case']['property']) for j in jobs)
        def snapshot(phase,errors=None):
            groups=[]
            for (setting,prop),n in expected.items():
                subset=[r for r in rows.values() if r['setting']==setting and r['case']['property']==prop]
                groups.append({'setting':setting,'property':prop,'expected':n,'processed':len(subset),
                    'success':sum(r['score']['success'] for r in subset),
                    'statuses':dict(collections.Counter(r['status'] for r in subset))})
            dump(ROOT/'summary.json',{'method':'GLM_direct','generation':manifest['generation'],
                'processed':len(rows),'expected':4200,'groups':groups,'updated':time.time()})
            state={'phase':phase,'processed':len(rows),'expected':4200,'workers':WORKERS,
                'generation':manifest['generation'],'model':MODEL,'time':time.time()}
            if errors:state['errors']=errors
            dump(ROOT/'state.json',state)
            print(json.dumps(state),flush=True)
        pilot=[];rest=[];seen=set()
        for job in jobs:
            case=job['case'];bucket=(job['setting'],case.get('task'),case.get('constraint'),case['property'])
            if bucket not in seen:pilot.append(job);seen.add(bucket)
            else:rest.append(job)
        snapshot('pilot')
        for phase,batch in [('pilot',pilot),('full',rest)]:
            pending=[j for j in batch if (j['setting'],j['case']['id']) not in rows]
            errors=[]
            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures={pool.submit(run_one,j):j for j in pending}
                for future in concurrent.futures.as_completed(futures):
                    job=futures[future]
                    if future.cancelled():continue
                    try:
                        row=future.result();rows[(row['setting'],row['id'])]=row
                    except Exception as error:
                        errors.append({'setting':job['setting'],'id':job['case']['id'],'error':str(error)})
                        if len(errors)==1:
                            for queued in futures:queued.cancel()
                    if errors or len(rows)%10==0:snapshot(phase,errors)
            if errors:
                snapshot('awaiting_quota' if any('PROVIDER_HOLD' in e['error'] for e in errors) else 'attention_required',errors)
                return 1
        assert len(rows)==4200
        snapshot('complete')
        return 0
if __name__=='__main__':sys.exit(main())
