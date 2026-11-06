from pathlib import Path
import argparse,concurrent.futures,fcntl,json,os,re,socket,subprocess,sys,time,traceback
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source_snapshot'))
from oracle_server import LEGACY,SUBMISSION,TASKS,canonical
from pmo_common import dump,sha
from trajectory import complete_auc
from stall_watchdog import run_native
from transport import Boundary
import requests
CODEX=Path('/data2/chenfuxin/smdd_codex_type2_bailian_20260929/bin/codex')
LITELLM=Path('/data2/chenfuxin/molclaw_20260924/isolated_env/bin/litellm')
MODEL='deepseek-v4.1-flash'

def sandbox(work):
    cmd=['bwrap','--die-with-parent','--new-session','--unshare-pid','--unshare-ipc','--unshare-uts']
    for p in ['/usr','/bin','/lib','/lib64','/etc']:cmd+=['--ro-bind',p,p]
    cmd+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--dir','/root','--ro-bind',str(CODEX),'/runner/codex','--bind',str(work),'/workspace','--chdir','/workspace','--clearenv']
    for k,v in {'PATH':'/usr/bin:/bin','HOME':'/workspace/.home','CODEX_HOME':'/workspace/.codex','PMO_LOCAL_KEY':'local-only'}.items():cmd+=['--setenv',k,v]
    return cmd

def command(work,port,mcp,session=None):
    values={'model_provider':'pmo','model_reasoning_effort':'none','model_reasoning_summary':'none','model_providers.pmo.name':'PMO DeepSeek','model_providers.pmo.base_url':f'http://127.0.0.1:{port}/v1','model_providers.pmo.env_key':'PMO_LOCAL_KEY','model_providers.pmo.wire_api':'responses','model_providers.pmo.requires_openai_auth':False,'model_providers.pmo.stream_idle_timeout_ms':300000,'model_providers.pmo.request_max_retries':2,'web_search':'disabled','features.shell_tool':False,'features.unified_exec':False,'features.multi_agent':False,'features.apps':False,'features.enable_request_compression':False,'features.memories':False,'mcp_servers.pmo.url':f'http://127.0.0.1:{mcp}/mcp','mcp_servers.pmo.tool_timeout_sec':600,'mcp_servers.pmo.startup_timeout_sec':30}
    cmd=sandbox(work)+['/runner/codex','exec']+(['resume'] if session else [])+['--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','--json','-m',MODEL]
    for k,v in values.items():cmd+=['-c',k+'='+json.dumps(v)]
    return cmd+([session] if session else [])+['-']

def finish(out,task,ledger,status,answer=None,reason=None):
    rows=ledger.rows
    auc,curve=complete_auc(rows,budget=len(rows)) if rows else (0.0,[])
    dump(out/'top10_trajectory.json',curve)
    result={'method':'codex','task':task,'seed':0,'status':status,'experiment_finished':status=='validated_finished','oracle_submissions':len(rows),'submission_budget':ledger.budget,'unique_valid':len(ledger.buffer),'invalid':sum(r['status']=='invalid' for r in rows),'duplicates':sum(r['status']=='duplicate' for r in rows),'auc_top10':auc if len(rows)==ledger.budget else None,'auc_top10_observed':auc,'auc_area_divided_by_budget':auc*len(rows)/ledger.budget,'auc_protocol':'actual submission trajectory; unique valid top10; trapezoid from zero; no unobserved tail','final_answer':answer,'reason':reason,'time':time.time()}
    dump(out/'result.json',result);return result

def retry_truncation(returncode, before, after, session):
    return bool(returncode and after > before and after < 3 and session)


def job(task,stage='full',budget=1000):
    os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.chdir(LEGACY)
    out=ROOT/'control'/stage/task/'0';work=ROOT/'runs'/stage/task/'0'
    out.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    (work/'.codex').mkdir(exist_ok=True);(work/'.home').mkdir(exist_ok=True)
    lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
    for p,digest in json.loads((LEGACY/'prepared/dependencies.json').read_text()).items():
        if sha(p)!=digest:raise RuntimeError('Oracle dependency changed: '+p)
    source=SUBMISSION/'runs/deepseek'/task/'0/answers.jsonl';seed=json.loads(source.read_text().splitlines()[0]);assert seed['index']==1
    state=json.loads((out/'state.json').read_text()) if (out/'state.json').exists() else {'session':None,'segment':0,'started':time.time()}
    if state.pop('recovery_pending',False):
        count=len((out/'oracle_queries.jsonl').read_text().splitlines())
        dump(out/'watchdog.json',{'count':count,'last_progress':time.time()})
        dump(out/'state.json',state)
    boundary=Boundary(out,work,task,budget)
    if not boundary.oracle.ledger().rows:boundary.oracle.score([seed['raw']],'initial_model_answer')
    initial=boundary.oracle.ledger().rows[0]
    assert initial['raw']==seed['raw'] and abs(initial['score']-seed['score'])<1e-10
    dump(out/'config.json',{'method':'codex','model':MODEL,'temperature':0,'enable_thinking':False,'task':task,'seed':0,'oracle_query_budget':budget,'initial_source':str(source),'initial_answer':seed['raw'],'initial_source_sha256':sha(source),'duplicate_queries_consume_budget':True,'invalid_queries_consume_budget':True,'shared_key_source':'/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env','source_hashes':{p.name:sha(p) for p in ROOT.glob('*.py')}})
    prompt=(f'PMO molecular optimization objective: {task}. {TASKS[task][1]} Scores range from 0 to 1; higher is better. '
        f'Improve this starting molecule: {seed["raw"]}. Its official score is {initial["score"]}. Initialization used 1 of {budget} shared oracle submissions. '
        'Use your native planning and context to explore candidates. All objective scores, reference evaluations and feedback must use the PMO score_molecules or score_file tools. '
        'Do not implement the objective or a surrogate locally, including Gaussian descriptor combinations or fingerprint similarity. Local structural generation, RDKit validation and individual property inspection are allowed through the PMO python tool. '
        f'Complete exactly {budget} actual scored candidate submissions; each invalid or duplicate submission counts. Do not stop even at score 1.0; explore and improve the top 10 diverse candidates. Do not pad the budget with deliberate repeats or invalid molecules. '
        'No other benchmark histories, pre-scored libraries or external services are available. Preserve this single session and ledger. '
        'Use budget_status to inspect progress. At exhaustion choose the best already evaluated molecule and return <answer>SMILES</answer>.')
    if stage=='pilot':prompt+=' This is a small independent transport and budget check. Exercise the Python tool for RDKit validation, and submit candidates through PMO tools to fill this small test budget.'
    (out/'initial_prompt.txt').write_text(prompt)
    server=boundary.service();proxy=None
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    config={'model_list':[{'model_name':'*','litellm_params':{'model':'openai/'+MODEL,'use_chat_completions_api':True,'api_base':f'http://127.0.0.1:{server.server_address[1]}/v1','api_key':'local-only'}}],'litellm_settings':{'drop_params':True,'set_verbose':False},'general_settings':{'disable_spend_logs':True}}
    dump(out/'proxy_config.json',config)
    try:
        with (out/'proxy.log').open('a') as log:
            proxy=subprocess.Popen([str(LITELLM),'--config',str(out/'proxy_config.json'),'--host','127.0.0.1','--port',str(port)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,LITELLM_LOCAL_MODEL_COST_MAP='True'))
        for _ in range(120):
            if proxy.poll() is not None:raise RuntimeError('Proxy startup failed')
            try:
                if requests.get(f'http://127.0.0.1:{port}/health/liveliness',timeout=1).status_code==200:break
            except requests.RequestException:pass
            time.sleep(1)
        else:raise RuntimeError('Proxy readiness timeout')
        for segment in range(state['segment'],2048):
            ledger=boundary.oracle.ledger()
            if segment:
                prompt=(f'Continue the SAME PMO session and ledger: {len(ledger.rows)} of {budget} submissions have been scored. Do not restart or replay evaluations. '
                        'If budget remains, continue generating candidates and calling the official PMO tools; do not deliberately pad with repeats or invalid molecules. '
                        'Only when the budget is exhausted, return exactly one best already evaluated molecule as <answer>SMILES</answer>.')
            cmd=command(work,port,server.server_address[1],state['session'])
            state.update(status='running',segment=segment,time=time.time(),pid=os.getpid());dump(out/'state.json',state)
            (out/f'prompt_{segment:04d}.txt').write_text(prompt)
            truncations_before=boundary.truncations
            with (out/f'events_{segment:04d}.jsonl').open('w') as log,(out/f'stderr_{segment:04d}.log').open('w') as err:
                proc=run_native(out,cmd,input=prompt,text=True,cwd=work,stdout=log,stderr=err)
            events=[]
            for line in (out/f'events_{segment:04d}.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            for event in events:
                if event.get('type')=='thread.started':state['session']=event['thread_id']
            state['segment']=segment+1;dump(out/'state.json',state)
            ledger=boundary.oracle.ledger()
            if proc.stalled:return finish(out,task,ledger,'skipped_stalled',reason='No newly scored submission for 30 minutes')
            if boundary.truncations>=3:return finish(out,task,ledger,'skipped_long_truncation',reason='Three provider-default output truncations')
            if retry_truncation(proc.returncode,truncations_before,boundary.truncations,state['session']):
                continue
            if proc.returncode:raise RuntimeError('Native Codex exited '+str(proc.returncode))
            messages=[e['item'].get('text','') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
            matches=re.findall(r'<answer>\s*(.*?)\s*</answer>',messages[-1] if messages else '',re.S)
            answer=canonical(matches[-1]) if len(matches)==1 else None
            if ledger.exhausted and answer in ledger.buffer:return finish(out,task,ledger,'validated_finished',answer)
            if not state['session']:raise RuntimeError('No native session id for continuation')
            state['segment']=segment+1;dump(out/'state.json',state)
        return finish(out,task,boundary.oracle.ledger(),'needs_attention',reason='2048 native continuation segments exhausted')
    except Exception as exc:
        dump(out/'error.json',{'error':str(exc),'traceback':traceback.format_exc()})
        return finish(out,task,boundary.oracle.ledger(),'error',reason=str(exc))
    finally:
        if proxy and proxy.poll() is None:proxy.terminate();proxy.wait(timeout=30)
        server.shutdown()

def summary(stage):
    rows={p.parent.parent.name:json.loads(p.read_text()) for p in (ROOT/'control'/stage).glob('*/0/result.json')}
    data={'stage':stage,'expected':23 if stage=='full' else 3,'processed':len(rows),'completed':sum(x['status']=='validated_finished' for x in rows.values()),'results':rows}
    dump(ROOT/(stage+'_summary.json'),data);return data

def suite(stage):
    tasks=list(TASKS) if stage=='full' else ['qed','drd2','amlodipine_mpo']
    budget=1000 if stage=='full' else 10
    with (ROOT/(stage+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            jobs={pool.submit(job,t,stage,budget):t for t in tasks}
            for future in concurrent.futures.as_completed(jobs):
                result=future.result();summary(stage)
                print(json.dumps({'task':jobs[future],'status':result['status'],'oracle_submissions':result['oracle_submissions']}),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full','status']);args=ap.parse_args()
    if args.stage=='status':print(json.dumps(summary('full')))
    else:suite(args.stage)
