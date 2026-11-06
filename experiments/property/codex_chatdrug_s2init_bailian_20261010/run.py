"""Native Codex CLI + DeepSeek Flash, frozen four-benchmark evaluation."""
import ast,collections,concurrent.futures,fcntl,hashlib,json,os,re,signal,subprocess,sys,time,shutil,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MOL=Path('/data2/chenfuxin/molclaw_20260924')
S2=Path('/data2/chenfuxin/s2_edit_custom_20260928')
LANG=Path('/data2/chenfuxin/mollangbench_20260928')
OLD=Path('/data2/chenfuxin/smdd_codex_type2_bailian_20260929')
MODEL='deepseek-v4.1-flash'

def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2));tmp.replace(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extract(path,names,ns):
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
def cases():return json.loads((ROOT/'cases.json').read_text())
def parse(text):
    tags=re.findall(r'<answer>\s*(.*?)\s*</answer>',text,re.S|re.I)
    if len(tags)!=1:return None
    value=tags[0].strip()
    return value if value and not any(c.isspace() for c in value) else None


def sandbox(work):
    cmd=['bwrap','--die-with-parent','--new-session','--unshare-pid','--unshare-ipc','--unshare-uts']
    paths=[Path(p) for p in ['/usr','/bin','/lib','/lib64','/etc','/opt/codex-node']]+[MOL/'isolated_env',Path('/data2/chenfuxin/chatdrug_generalization_20260920/venv'),OLD/'deps']
    for p in paths:
        if p.exists():cmd+=['--ro-bind',str(p),str(p)]
    cmd+=['--ro-bind',str(OLD/'bin/codex'),'/runner/codex','--ro-bind','/usr/bin/python3.10','/data2/chenfuxin/smdd-boltz-env/bin/python',
          '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--dir','/root','--bind',str(work),'/workspace','--chdir','/workspace','--clearenv']
    env={'HOME':'/workspace/.home','CODEX_HOME':'/workspace/.codex','PATH':str(Path('/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin'))+':/usr/local/bin:/usr/bin:/bin','PYTHONPATH':'','BAILIAN_API_KEY':'local-only','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    for k,v in env.items():cmd+=['--setenv',k,v]
    return cmd

def command(work,port):
    values={'model_provider':'bailian','model_providers.bailian.name':'Bailian DeepSeek original mol-edit','model_providers.bailian.base_url':f'http://127.0.0.1:{port}/v1','model_providers.bailian.env_key':'BAILIAN_API_KEY','model_providers.bailian.wire_api':'responses','model_providers.bailian.requires_openai_auth':False,'model_providers.bailian.request_max_retries':2,'model_providers.bailian.stream_max_retries':2,'model_providers.bailian.stream_idle_timeout_ms':300000,'web_search':'disabled','features.memories':False,'features.apps':False,'features.multi_agent':False,'features.enable_request_compression':False}
    cmd=sandbox(work)+['/runner/codex','exec','--ephemeral','--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','--json','-m',MODEL]
    for k,v in values.items():cmd+=['-c',k+'='+json.dumps(v)]
    return cmd+['-o','/workspace/last_message.txt','-']

def execute(c,stage,prompt_override=None):
    from bridge import Bridge
    out=ROOT/'runs'/stage/c['id'];work=ROOT/'work'/stage/c['id']
    out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
    if (out/'started.json').exists():
        row={'id':c['id'],'bench':c['bench'],'bucket':c['bucket'],'status':'interrupted','candidate':None}
        dump(out/'result.json',row);return row
    while shutil.disk_usage(ROOT).free<20*1024**3:
        dump(out/'resource_wait.json',{'state':'waiting_disk','native_budget_started':False,'time':time.time()})
        time.sleep(15)
    (out/'resource_wait.json').unlink(missing_ok=True)
    work.mkdir(parents=True,exist_ok=True)
    (work/'.home').mkdir(exist_ok=True);(work/'.codex').mkdir(exist_ok=True)
    prompt=c['instruction']+'\n\nWork only in /workspace. Python with RDKit is available for your own structural calculations. Do not access hidden answers, evaluators, prior experiment results, or other task directories. Submit exactly ONE final molecule as <answer>SMILES</answer> in your final response.'
    if prompt_override is not None:prompt=prompt_override
    (out/'prompt.txt').write_text(prompt)
    proc=None;timed_out=False;timeout_reason=None
    try:
        with Bridge(out) as bridge:
            started=time.time();cmd=command(work,bridge.port)
            dump(out/'started.json',{'started':started,'command':cmd,'model':MODEL})
            with (out/'events.jsonl').open('w') as log,(out/'stderr.log').open('w') as err:
                proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=log,stderr=err,text=True,start_new_session=True)
                dump(out/'process.json',{'pid':proc.pid,'started':started})
                first=True
                while True:
                    try:proc.communicate(input=prompt if first else None,timeout=20);break
                    except subprocess.TimeoutExpired:
                        first=False;now=time.time()
                        idle=now-max(started,(out/'events.jsonl').stat().st_mtime)
                        if now-started>3600 or idle>1800:
                            timed_out=True;timeout_reason='wall_3600s' if now-started>3600 else 'idle_1800s'
                            os.killpg(proc.pid,signal.SIGTERM)
                            try:proc.wait(timeout=10)
                            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                            break
            events=[]
            for line in (out/'events.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            text=(work/'last_message.txt').read_text() if (work/'last_message.txt').exists() else ''
            final=next((e for e in reversed(events) if e.get('type') in ('turn.completed','turn.failed')), {})
            status='timeout' if timed_out else ('complete' if proc.returncode==0 and final.get('type')=='turn.completed' else 'error')
            records=[json.loads(p.read_text()) for p in sorted((out/'api').glob('*.json'))]
            if status=='error' and records and 'truncated' in str(records[-1].get('error','')).lower():status='provider_limit'
            tools=sum(e.get('type')=='item.completed' and e.get('item',{}).get('type') in ('command_execution','mcp_tool_call','tool_call','file_change') for e in events)
            row={'id':c['id'],'bench':c['bench'],'bucket':c['bucket'],'status':status,
                 'method':'codex','model':MODEL,'candidate':parse(text) if status=='complete' else None,
                 'output':text,'returncode':proc.returncode,'error':final.get('error'),
                 'timeout_reason':timeout_reason,'usage':final.get('usage',{}),'tool_calls':tools,
                 'llm_requests':len(records),'provider_truncations':bridge.relay.truncations,
                 'seconds':time.time()-started}
    except Exception as exc:
        (out/'exception.log').write_text(traceback.format_exc())
        row={'id':c['id'],'bench':c['bench'],'bucket':c['bucket'],'status':'error',
             'method':'codex','model':MODEL,'candidate':None,'error':type(exc).__name__}
    finally:
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    dump(out/'result.json',row)
    print(json.dumps({k:row.get(k) for k in ('id','status','candidate','tool_calls')}),flush=True)
    return row



def summary(stage,selected):
    rows=[json.loads(p.read_text()) for p in (ROOT/'runs'/stage).glob('*/result.json')];groups={}
    for bench,n in collections.Counter(c['bench'] for c in selected).items():
        rr=[r for r in rows if r['bench']==bench]
        groups[bench]={'expected':n,'processed':len(rr),'runtime_errors':sum(r['status'] not in ('complete','provider_limit','timeout') for r in rr),'missing_submission':sum(not r.get('candidate') for r in rr)}
    result={'processed':len(rows),'expected':len(selected),'groups':groups,'updated':time.time()};dump(ROOT/'runs'/stage/'summary.json',result)
    return result

def main(stage):
    selected=cases()
    if stage=='pilot':selected=[next(c for c in selected if c['benchmark']==name) for name in ('ChatDrug','S2-mini')]
    if stage=='full':
        groups=[[c for c in selected if c['benchmark']==name] for name in ('ChatDrug','S2-mini')]
        selected=[g[i] for i in range(max(map(len,groups))) for g in groups if i<len(g)]
    with (ROOT/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);summary(stage,selected)
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            futures=[pool.submit(execute,c,stage) for c in selected]
            for f in concurrent.futures.as_completed(futures):f.result();summary(stage,selected)
    if stage=='pilot' and any(g['runtime_errors'] for g in summary(stage,selected)['groups'].values()):raise RuntimeError('Pilot infrastructure failure; full blocked')

if __name__=='__main__':main(sys.argv[1])
