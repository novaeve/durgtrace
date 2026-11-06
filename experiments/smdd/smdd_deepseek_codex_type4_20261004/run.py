"""Native MolClaw/Codex, with a common SMDD tool and DeepSeek transport boundary."""
from pathlib import Path
import argparse,ast,fcntl,hashlib,http.server,inspect,json,os,shutil,socket,subprocess,sys,threading,time,traceback
ROOT=Path(__file__).resolve().parent
BASE=ROOT
MOL=Path('/data2/chenfuxin/molclaw_20260924')
CODEX=ROOT/'bin/codex'
sys.path.insert(0,str(BASE))
import runtime,requests,yaml
from runtime import API,Executor,dump
from agent_harness.config import AgentConfig
from agent_harness.prompts import TOOL_SCHEMAS,build_system_prompt
from agent_harness.obfuscate import obfuscate_task

def configure_gpu():
    os.environ['PYTORCH_CUDA_ALLOC_CONF']='expandable_segments:True'

class Boundary:
    def __init__(self,out,work):
        self.out=out;self.api=API(out);self.executor=Executor(str(work),AgentConfig());self.lock=threading.Lock();self.tool_lock=threading.Lock();self.submitted=False;self.error=None;self.tools=0
    def service(self):
        state=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,obj,status=200):
                data=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_GET(self):self.send({'status':'ok'} if self.path=='/health' else {},200 if self.path=='/health' else 405)
            def do_DELETE(self):self.send({})
            def do_POST(self):
                try:
                    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                    if self.path=='/mcp':
                        method=body.get('method');rid=body.get('id');params=body.get('params',{})
                        if rid is None:self.send_response(202);self.end_headers();return
                        if method=='initialize':result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'smdd-common-tools','version':'1.0'}}
                        elif method=='ping':result={}
                        elif method=='tools/list':result={'tools':[{'name':t['name'],'description':t['description'],'inputSchema':t['parameters']} for t in TOOL_SCHEMAS]}
                        elif method=='tools/call':
                            with state.tool_lock:
                                name=params['name'];args=params.get('arguments',{})
                                if name not in [t['name'] for t in TOOL_SCHEMAS]:raise ValueError('Unknown tool')
                                if state.submitted:raise ValueError('Task already submitted')
                                state.tools+=1;start=time.time();text,extra=state.executor.dispatch(name,args)
                                if name=='submit' and text.startswith('Submission accepted:'):state.submitted=True
                                dump(state.out/'tools'/f'{state.tools:03d}.json',{'name':name,'arguments':args,'result':text,'extra':extra,'started':start,'ended':time.time()})
                                result={'content':[{'type':'text','text':text}]}
                        else:self.send({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Unsupported method'}});return
                        self.send({'jsonrpc':'2.0','id':rid,'result':result});return
                    if not self.path.split('?')[0].rstrip('/').endswith('/chat/completions'):
                        dump(state.out/'unhandled_protocol.json',{'path':self.path,'keys':list(body)})
                        self.send({'error':'Not found'},404);return
                    with state.lock:
                        if state.api.calls>=100 or state.api.total_tokens>=10000000:
                            state.error='budget_exhausted';self.send({'error':{'message':'SMDD cumulative budget exhausted','type':'budget_exhausted'}},400);return
                        data=state.api.complete(body['messages'],tools=body.get('tools'),temperature=1)
                    if not body.get('stream'):self.send(data);return
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
                    msg=data['choices'][0]['message'];delta=dict(msg)
                    if delta.get('tool_calls'):delta['tool_calls']=[dict(t,index=i) for i,t in enumerate(delta['tool_calls'])]
                    chunk={'id':data['id'],'object':'chat.completion.chunk','created':data.get('created',int(time.time())),'model':data['model'],'choices':[{'index':0,'delta':delta,'finish_reason':None}]}
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
                    chunk['choices']=[{'index':0,'delta':{},'finish_reason':data['choices'][0].get('finish_reason','stop')}];chunk['usage']=data.get('usage',{})
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass
                except Exception as exc:
                    state.error=type(exc).__name__+': '+str(exc)
                    dump(state.out/'boundary_error.json',{'error':state.error,'traceback':traceback.format_exc()})
                    try:self.send({'error':{'message':state.error}},500)
                    except OSError:pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start();return server

def freeport():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def sandbox(work,port):
    args=['bwrap','--die-with-parent','--new-session','--unshare-pid','--unshare-ipc','--unshare-uts']
    for p in ['/usr','/bin','/lib','/lib64','/etc','/opt/codex-node']:
        if Path(p).exists():args+=['--ro-bind',p,p]
    args+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--dir','/root','--ro-bind',str(CODEX),'/runner/codex','--bind',str(work),'/workspace','--chdir','/workspace','--clearenv']
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/workspace/.home','CODEX_HOME':'/workspace/.codex','BAILIAN_API_KEY':'local-only','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    for k,v in env.items():args+=['--setenv',k,v]
    return args

def command(method,work,port,mcp,prompt):
    values={'model_provider':'smdd','model_providers.smdd.name':'SMDD DeepSeek boundary','model_providers.smdd.base_url':f'http://127.0.0.1:{port}/v1','model_providers.smdd.env_key':'BAILIAN_API_KEY','model_providers.smdd.wire_api':'responses','model_providers.smdd.requires_openai_auth':False,'model_providers.smdd.stream_idle_timeout_ms':900000,'model_providers.smdd.request_max_retries':2,'web_search':'disabled','features.shell_tool':False,'features.unified_exec':False,'features.multi_agent':False,'features.apps':False,'features.enable_request_compression':False,'features.memories':False,'mcp_servers.smdd.url':f'http://127.0.0.1:{mcp}/mcp','mcp_servers.smdd.tool_timeout_sec':28800,'mcp_servers.smdd.startup_timeout_sec':30,'developer_instructions':build_system_prompt(AgentConfig())}
    cmd=sandbox(work,port)+['/runner/codex','exec','--ephemeral','--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','--json','-m','deepseek-v4.1-flash']
    for k,v in values.items():cmd+=['-c',k+'='+json.dumps(v)]
    return cmd+['-o','/workspace/last_message.txt','-'],prompt

def job(method,tid,index,smoke=False):
    out=ROOT/('preflight' if smoke else 'runs')/method/tid;out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
    work=out/'workspace'
    if work.exists():raise RuntimeError('Unfinished attempt; inspect/archive before retry: '+str(out))
    work.mkdir();(work/'.home').mkdir();(work/'.codex').mkdir()
    public=BASE/'public_inputs'/tid
    assert {p.name for p in public.iterdir()}=={'complex.pdb','reference.sdf'}
    for p in public.iterdir():shutil.copyfile(p,work/p.name)
    task=json.loads((BASE/'tasks'/f'{tid}.json').read_text())
    prompt=f"## Task\n\n{task['description']}\n\nYour workspace at /workspace contains the task files. Start by examining them."
    if smoke:prompt='Use the SMDD python tool to import rdkit and write the result of 17*19 into probe.txt. Read it back with that tool. Finish saying SMOKE_OK. Do not solve the molecule task.'
    (out/'prompt.txt').write_text(prompt)
    boundary=Boundary(out,work);server=boundary.service();port=freeport()
    cfg={'model_list':[{'model_name':'*','litellm_params':{'model':'openai/deepseek-v4.1-flash','use_chat_completions_api':True,'api_base':f'http://127.0.0.1:{server.server_address[1]}/v1','api_key':'local-only','extra_body':{'enable_thinking':False}}}],'litellm_settings':{'drop_params':True,'set_verbose':False,'use_chat_completions_url_for_anthropic_messages':True},'general_settings':{'disable_spend_logs':True}}
    dump(out/'proxy_config.json',cfg)
    start=time.time();proxy=None
    try:
        with (out/'proxy.log').open('w') as log:
            proxy=subprocess.Popen([str(MOL/'isolated_env/bin/litellm'),'--config',str(out/'proxy_config.json'),'--host','127.0.0.1','--port',str(port)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        for _ in range(120):
            if proxy.poll() is not None:raise RuntimeError('LiteLLM startup failed')
            try:
                if requests.get(f'http://127.0.0.1:{port}/health/liveliness',timeout=1).status_code==200:break
            except requests.RequestException:pass
            time.sleep(1)
        else:raise RuntimeError('LiteLLM readiness timeout')
        cmd,prompt=command(method,work,port,server.server_address[1],prompt)
        dump(out/'started.json',{'time':start,'task':tid,'method':method,'command':cmd,'public_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in public.iterdir()}})
        with (out/'events.jsonl').open('w') as log,(out/'stderr.log').open('w') as err:
            proc=subprocess.run(cmd,input=prompt,text=True,stdout=log,stderr=err,timeout=43200)
        status='complete' if proc.returncode==0 else ('budget_exhausted' if boundary.error=='budget_exhausted' else 'error')
        if smoke:status='complete' if status=='complete' and (work/'probe.txt').exists() and (work/'probe.txt').read_text().strip()=='323' and boundary.tools>=1 else 'error'
        if (work/'solution.smi').exists():shutil.copyfile(work/'solution.smi',out/'solution.smi')
        result={'status':status,'method':method,'task':tid,'exit_code':proc.returncode,'calls':boundary.api.calls,'tokens':boundary.api.total_tokens,'tool_calls':boundary.tools,'boltz_calls':boundary.executor.boltz_calls,'admet_calls':boundary.executor.admet_calls,'submitted':boundary.submitted,'boundary_error':boundary.error,'started':start,'ended':time.time()}
    except Exception as exc:
        result={'status':'error','method':method,'task':tid,'error':str(exc)};(out/'error.log').write_text(traceback.format_exc())
    finally:
        if proxy is not None and proxy.poll() is None:proxy.terminate();proxy.wait(timeout=30)
        server.shutdown()
    dump(out/'result.json',result);print(json.dumps(result),flush=True);return result

def main():
    a=argparse.ArgumentParser();a.add_argument('method',choices=['codex','deepseek']);a.add_argument('--task',required=True);a.add_argument('--smoke',action='store_true');args=a.parse_args()
    configure_gpu()
    if args.method=='deepseek':
        out=ROOT/('preflight' if args.smoke else 'runs')/'deepseek'/args.task;out.mkdir(parents=True,exist_ok=True)
        task=json.loads((ROOT/'tasks'/f'{args.task}.json').read_text())
        result=runtime.baseline(task,ROOT/'public_inputs'/args.task,out)
        dump(out/'result.json',result)
    else:result=job('codex',args.task,0,args.smoke)
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
