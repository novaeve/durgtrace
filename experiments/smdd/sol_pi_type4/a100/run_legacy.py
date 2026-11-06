"""Native, unmodified Pi and SoL-Pi with official SMDD tool/budget boundaries."""
from pathlib import Path
import sys,os,json,threading,http.server,subprocess,shutil,time,traceback,shlex,hashlib,signal
ROOT=Path(__file__).resolve().parent
SOL=ROOT/'SoL-Pi'
from runtime import API,Executor,dump
from agent_harness.config import AgentConfig
from agent_harness.prompts import TOOL_SCHEMAS,build_system_prompt
MODEL='deepseek-v4.1-flash'
FLAGS=dict(version=1,actionFusion=True,observationPack=True,evidencePreservingReducer=True,onlineContextCompact=True,evidencePreservingReducerProvider='smdd-deepseek',evidencePreservingReducerModel=MODEL,cacheWriteReadRatio=12.5)
def guard(name,inputs):
 protected=['.agent/','.pi/sol-pi.json','.pi/session.jsonl','.pi/loaded-runtime.json']
 if name in ['write','edit']:
  path=str(inputs.get('path','')).removeprefix('/workspace/').removeprefix('./')
  if any(path.startswith(p) for p in protected):return 'Runtime configuration and evidence are managed by the experiment.'
 if name in ['read','write','edit','grep','find','ls'] and inputs.get('path'):
  p=str(inputs['path'])
  if '..' in Path(p).parts or (p.startswith('/') and not p.startswith('/workspace/')):return 'Use only the task workspace.'
 command=str(inputs.get('command','')) if name=='bash' else ''
 follow=inputs.get('then_run')
 if follow:command+=' '+str(follow.get('command','') if isinstance(follow,dict) else follow)
 if command:
  denied=['curl','wget','pip','pip3','npm','npx','node','ssh','sftp','docker','boltz','eval_entrypoint','admet_ai','ADMETModel','torch.load','/eval','/data2','/yimin','/proc/','/agent','/opt/bridge','/opt/sol-pi','..','/etc/','socket','urllib','requests','http://','https://','/workspace/.agent','/workspace/.pi/session']
  if any(x in command for x in denied):return 'Use benchmark prediction tools and workspace-only analysis; runtime, network and oracle internals are unavailable.'
 return None
class Boundary:
 def __init__(self,out,work):
  self.out=out;self.api=API(out);self.executor=Executor(str(work),AgentConfig());self.lock=threading.Lock();self.tool_lock=threading.Lock();self.submitted=False;self.error=None;self.tools=0
 def service(self):
  state=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def send(self,obj,status=200):
    data=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
   def do_POST(self):
    try:
     body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
     if self.path=='/mcp':
      rid=body.get('id');params=body.get('params',{});name=params.get('name');args=params.get('arguments',{})
      if name=='protocol_guard':
       reason=guard(args['name'],args.get('input') or {})
       with (state.out/'guard_events.jsonl').open('a') as f:f.write(json.dumps({'tool':args['name'],'reason':reason,'time':time.time()})+'\n')
       text=json.dumps({'reason':reason})
      else:
       with state.tool_lock:
        if name not in [t['name'] for t in TOOL_SCHEMAS]:raise ValueError('Unknown SMDD tool')
        if state.submitted:raise ValueError('Task already submitted')
        state.tools+=1;start=time.time();text,extra=state.executor.dispatch(name,args)
        if name=='submit' and text.startswith('Submission accepted:'):state.submitted=True
        dump(state.out/'tools'/f'{state.tools:03d}.json',{'name':name,'arguments':args,'result':text,'extra':extra,'started':start,'ended':time.time()})
      self.send({'jsonrpc':'2.0','id':rid,'result':{'content':[{'type':'text','text':text}]}});return
     if not self.path.rstrip('/').endswith('/chat/completions'):self.send({'error':'Not found'},404);return
     with state.lock:
      if state.api.calls>=100 or state.api.total_tokens>=10000000:
       state.error='budget_exhausted';self.send({'error':{'message':'SMDD shared model budget exhausted','type':'budget_exhausted'}},400);return
      data=state.api.complete(body['messages'],tools=body.get('tools'),temperature=1)
     if not body.get('stream'):self.send(data);return
     self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
     delta=dict(data['choices'][0]['message'])
     if delta.get('tool_calls'):delta['tool_calls']=[dict(t,index=i) for i,t in enumerate(delta['tool_calls'])]
     chunk={'id':data['id'],'object':'chat.completion.chunk','created':data.get('created',int(time.time())),'model':data['model'],'choices':[{'index':0,'delta':delta,'finish_reason':None}]}
     self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
     chunk['choices']=[{'index':0,'delta':{},'finish_reason':data['choices'][0].get('finish_reason','stop')}];chunk['usage']=data.get('usage',{})
     self.wfile.write(('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush();self.close_connection=True
    except (BrokenPipeError,ConnectionResetError):pass
    except Exception as exc:
     state.error=type(exc).__name__+': '+str(exc)
     dump(state.out/'boundary_error.json',{'error':state.error,'traceback':traceback.format_exc()})
     try:self.send({'error':{'message':state.error}},500)
     except OSError:pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();return server
def command(work,port,models=False):
 args=['bwrap','--die-with-parent','--new-session','--unshare-pid','--cap-drop','ALL']
 for p in ['/usr','/bin','/lib','/lib64','/etc']:args+=['--ro-bind',p,p]
 args+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--dir','/home/agent','--ro-bind',str(SOL),'/opt/sol-pi','--ro-bind',str(ROOT/'node'),'/opt/codex-node','--ro-bind',str(ROOT/'bridge'),'/opt/bridge','--bind',str(work),'/workspace','--bind',str(work/'.agent'),'/agent','--chdir','/workspace','--clearenv']
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/agent','PI_CODING_AGENT_DIR':'/agent','PI_OFFLINE':'1','SMDD_BOUNDARY_URL':f'http://127.0.0.1:{port}','OPENSSL_CONF':'/dev/null','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
 for k,v in env.items():args+=['--setenv',k,v]
 args+=['/opt/codex-node/bin/node','/opt/sol-pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js','--offline','--approve','--no-extensions','--no-skills','--no-prompt-templates','--no-themes','--no-context-files','-e','/opt/bridge/smdd.ts','-e','/opt/sol-pi/src/sol-pi/index.ts','--provider','smdd-deepseek','--model',MODEL,'--thinking','off']
 if models:return args+['--list-models',MODEL]
 return args+['--mode','json','--print','--session','/workspace/.pi/session.jsonl','--append-system-prompt',build_system_prompt(AgentConfig())]
def prepare(work):
 (work/'.agent').mkdir(parents=True,exist_ok=True);(work/'.pi').mkdir(exist_ok=True)
 dump(work/'.agent/sol-pi.json',FLAGS)
 dump(work/'.agent/settings.json',{'quietStartup':True,'packages':['/opt/sol-pi'],'compaction':{'enabled':True},'retry':{'enabled':True,'maxRetries':3}})
 for name in ['rg','fd']:
  p=Path.home()/'.pi/agent/bin'/name;target=work/'.agent/bin'/name;target.parent.mkdir(exist_ok=True)
  if p.exists():shutil.copy2(p,target)
def job(tid,smoke=False):
 out=ROOT/('preflight' if smoke else 'runs')/'solpi'/tid;out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 work=out/'workspace'
 if work.exists():raise RuntimeError('Existing unfinished attempt; refusing duplicate execution')
 prepare(work)
 for p in (ROOT/'public_inputs'/tid).iterdir():shutil.copy2(p,work/p.name)
 description=json.loads((ROOT/'tasks'/f'{tid}.json').read_text())['description']
 prompt=f"## Task\n\n{description}\n\nYour workspace at /workspace contains the task files. Start by examining them."
 if smoke:prompt='Use the SMDD python tool to import rdkit, compute 17*19 and create probe.txt containing 323. Read it back using that tool. Use native write to create fused.txt and then_run to validate it using wc. Use update_plan to track this small test. Finish saying SMOKE_OK. Do not solve the molecule task.'
 (out/'prompt.txt').write_text(prompt);boundary=Boundary(out,work);server=boundary.service();started=time.time()
 try:
  with (out/'events.jsonl').open('w') as log,(out/'stderr.log').open('w') as err:
   p=subprocess.Popen(command(work,server.server_address[1]),stdin=subprocess.PIPE,stdout=log,stderr=err,text=True,start_new_session=True)
   dump(out/'process.json',{'pid':p.pid,'started':started})
   try:p.communicate(input=prompt,timeout=43200)
   except subprocess.TimeoutExpired:
    os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30);raise RuntimeError('Task watchdog exceeded 12 hours')
  status='complete' if p.returncode==0 else 'budget_exhausted' if boundary.error=='budget_exhausted' else 'error'
  if smoke and (not (work/'probe.txt').exists() or (work/'probe.txt').read_text().strip()!='323'):status='error'
  if (work/'solution.smi').exists():shutil.copy2(work/'solution.smi',out/'solution.smi')
  result={'status':status,'method':'solpi','task':tid,'exit':p.returncode,'model':MODEL,'enable_thinking':False,'temperature':1,'submitted':boundary.submitted,'calls':boundary.api.calls,'tokens':boundary.api.total_tokens,'boltz_calls':boundary.executor.boltz_calls,'admet_calls':boundary.executor.admet_calls,'tool_calls':boundary.tools,'error':boundary.error,'started':started,'ended':time.time()}
 except Exception as exc:
  (out/'error.log').write_text(traceback.format_exc());result={'status':'error','error':str(exc),'task':tid,'method':'solpi'}
 finally:server.shutdown()
 dump(out/'result.json',result);print(json.dumps(result),flush=True);return result
if __name__=='__main__':job(sys.argv[1],'--smoke' in sys.argv)
