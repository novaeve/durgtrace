"""SMDD transport repair: durable budgets, long HTTP tools, terminal submission."""
from pathlib import Path
import sys,os,json,time,threading,http.server,shutil,hashlib,signal,subprocess,traceback
from runtime import ROOT,API,Executor,dump
from agent_harness.config import AgentConfig
from agent_harness.prompts import TOOL_SCHEMAS
from run_legacy import MODEL,FLAGS,SOL,guard,prepare,command

def restored_state(out):
 state=dict(calls=0,tokens=0,admet_calls=0,boltz_calls=0,tool_calls=0,submitted=False)
 for name in ['resume_state.json','budget_state.json']:
  p=out/name
  if p.exists():
   d=json.loads(p.read_text())
   for k in state:
    if k in d:state[k]=max(state[k],d[k])
 receipts=[json.loads(p.read_text()) for p in (out/'api').glob('*.json')]
 state['calls']=max([state['calls']]+[int(p.stem) for p in (out/'api').glob('*.json')])
 state['tokens']=max(state['tokens'],sum(d.get('response',{}).get('usage',{}).get('total_tokens',0) for d in receipts))
 for p in (out/'tools').glob('*.json'):
  d=json.loads(p.read_text());state['tool_calls']=max(state['tool_calls'],int(p.stem))
  k={'predict_admet':'admet_calls','predict_boltz':'boltz_calls'}.get(d['name'])
  if k:state[k]=max(state[k],d.get('extra',{}).get('call_number',0))
  if d['name']=='submit' and d['result'].startswith('Submission accepted:'):state['submitted']=True
 return state

class Boundary:
 def __init__(self,out,work):
  self.out=out;self.work=work;self.api=API(out);self.executor=Executor(str(work),AgentConfig());self.lock=threading.Lock();self.tool_lock=threading.Lock();self.checkpoint_lock=threading.Lock();self.error=None;self.receipts={}
  d=restored_state(out);self.api.calls=d['calls'];self.api.total_tokens=d['tokens'];self.executor.admet_calls=d['admet_calls'];self.executor.boltz_calls=d['boltz_calls'];self.tools=d['tool_calls'];self.submitted=d['submitted']
  for p in (out/'api').glob('*.json'):
   for c in json.loads(p.read_text()).get('response',{}).get('choices',[]):
    m=c['message']
    for call in m.get('tool_calls') or []:self.api.reasoning[call['id']]=m.get('reasoning_content','')
  for p in (out/'tools').glob('*.json'):
   d=json.loads(p.read_text())
   if d.get('request_id') is not None:self.receipts[str(d['request_id'])]=(d['name'],d['arguments'],d['result'])
 def checkpoint(self,pending=None):
  d={'calls':self.api.calls,'tokens':self.api.total_tokens,'admet_calls':self.executor.admet_calls,'boltz_calls':self.executor.boltz_calls,'tool_calls':self.tools,'submitted':self.submitted,'time':time.time()}
  if pending:
   name,args=pending;k={'predict_admet':'admet_calls','predict_boltz':'boltz_calls'}.get(name)
   if k and d[k]<getattr(self.executor.config,{'admet_calls':'admet_budget','boltz_calls':'boltz_budget'}[k]):d[k]+=1
   d['pending_tool']={'name':name,'arguments':args}
  with self.checkpoint_lock:dump(self.out/'budget_state.json',d)
 def dispatch(self,rid,name,args):
  with self.tool_lock:
   if name not in [t['name'] for t in TOOL_SCHEMAS]:raise ValueError('Unknown SMDD tool')
   if str(rid) in self.receipts:
    old_name,old_args,text=self.receipts[str(rid)]
    if (name,args)!=(old_name,old_args):raise ValueError('Tool request ID reused with different arguments')
    return text
   if self.submitted:return 'Submission accepted: solution.smi. Task complete; original submission retained.'
   self.tools+=1;start=time.time();self.checkpoint((name,args));text,extra=self.executor.dispatch(name,args)
   if name=='submit' and text.startswith('Submission accepted:'):
    src=self.executor.path(args['file_path']);shutil.copy2(src,self.out/'accepted_solution.smi')
    dump(self.out/'submission.json',{'file_path':args['file_path'],'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'accepted':time.time()});self.submitted=True
   dump(self.out/'tools'/f'{self.tools:03d}.json',{'request_id':rid,'name':name,'arguments':args,'result':text,'extra':extra,'started':start,'ended':time.time()})
   self.receipts[str(rid)]=(name,args,text);self.checkpoint();return text
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
       text=json.dumps({'reason':reason,'taskComplete':state.submitted})
      else:text=state.dispatch(rid,name,args)
      self.send({'jsonrpc':'2.0','id':rid,'result':{'content':[{'type':'text','text':text}],'taskComplete':state.submitted}});return
     if not self.path.rstrip('/').endswith('/chat/completions'):self.send({'error':'Not found'},404);return
     with state.lock:
      if state.submitted:
       data={'id':'smdd-submitted','created':int(time.time()),'model':MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':'Submission accepted. Task complete.'},'finish_reason':'stop'}],'usage':{'total_tokens':0,'prompt_tokens':0,'completion_tokens':0}}
      else:
       if state.api.calls>=100 or state.api.total_tokens>=10000000:
        state.error='budget_exhausted';self.send({'error':{'message':'SMDD shared model budget exhausted','type':'budget_exhausted'}},400);return
       data=state.api.complete(body['messages'],tools=body.get('tools'),temperature=1);state.checkpoint()
     if not body.get('stream'):self.send(data);return
     self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
     delta=dict(data['choices'][0]['message'])
     if delta.get('tool_calls'):delta['tool_calls']=[dict(t,index=i) for i,t in enumerate(delta['tool_calls'])]
     chunk={'id':data['id'],'object':'chat.completion.chunk','created':data.get('created',int(time.time())),'model':data['model'],'choices':[{'index':0,'delta':delta,'finish_reason':None}]}
     self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode());chunk['choices']=[{'index':0,'delta':{},'finish_reason':data['choices'][0].get('finish_reason','stop')}];chunk['usage']=data.get('usage',{})
     self.wfile.write(('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush();self.close_connection=True
    except (BrokenPipeError,ConnectionResetError):pass
    except Exception as exc:
     state.error=type(exc).__name__+': '+str(exc);dump(state.out/'boundary_error.json',{'error':state.error,'traceback':traceback.format_exc()})
     try:self.send({'error':{'message':state.error}},500)
     except OSError:pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();return server

def job(tid,smoke=False,resume=False,prompt_override=None):
 out=ROOT/('preflight' if smoke else 'runs')/'solpi'/tid;out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 work=out/'workspace'
 if work.exists() and not resume:raise RuntimeError('Existing unfinished attempt; refusing duplicate execution')
 if resume:assert work.exists() and (work/'.pi/session.jsonl').exists(),'Resume requires an existing native session'
 else:
  prepare(work)
  for p in (ROOT/'public_inputs'/tid).iterdir():shutil.copy2(p,work/p.name)
 description=json.loads((ROOT/'tasks'/f'{tid}.json').read_text())['description']
 prompt=f'## Task\n\n{description}\n\nYour workspace at /workspace contains the task files. Start by examining them.'
 if smoke:prompt='Use SMDD python to import rdkit and create probe.txt containing 323. Read it back. Use native write with then_run to validate fused.txt using wc. Use update_plan. Finish saying SMOKE_OK. Do not solve the molecule task.'
 if resume:prompt='The SMDD tool transport has been repaired. Continue the original task from this saved session and workspace. All consumed model, ADMET and Boltz budgets are retained. Use SMDD python for RDKit. Submit the final molecule using the submit tool.'
 if prompt_override:prompt=prompt_override
 (out/('resume_prompt.txt' if resume else 'prompt.txt')).write_text(prompt);boundary=Boundary(out,work);server=boundary.service();started=time.time();proc=None
 try:
  if boundary.submitted:
   accepted=out/'accepted_solution.smi'
   if not accepted.exists():shutil.copy2(work/'solution.smi',accepted)
   exit_code=0
  else:
   with (out/'events.jsonl').open('a' if resume else 'w') as log,(out/'stderr.log').open('a' if resume else 'w') as err:
    proc=subprocess.Popen(command(work,server.server_address[1]),stdin=subprocess.PIPE,stdout=log,stderr=err,text=True,start_new_session=True)
    dump(out/'process.json',{'pid':proc.pid,'started':started});proc.stdin.write(prompt);proc.stdin.close();deadline=time.monotonic()+43200;accepted_at=None
    while proc.poll() is None:
     if boundary.submitted:
      accepted_at=accepted_at or time.monotonic()
      if time.monotonic()-accepted_at>3:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=30);break
     if time.monotonic()>deadline:
      os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=30);raise RuntimeError('Task watchdog exceeded 12 hours')
     time.sleep(0.2)
    exit_code=proc.returncode
  status='complete' if boundary.submitted or exit_code==0 else 'budget_exhausted' if boundary.error=='budget_exhausted' else 'error'
  if smoke and (not (work/'probe.txt').exists() or (work/'probe.txt').read_text().strip()!='323'):status='error'
  final=out/'accepted_solution.smi' if boundary.submitted else work/'solution.smi'
  if final.exists():shutil.copy2(final,out/'solution.smi')
  boundary.checkpoint();result={'status':status,'method':'solpi','task':tid,'exit':exit_code,'model':MODEL,'enable_thinking':False,'temperature':1,'submitted':boundary.submitted,'calls':boundary.api.calls,'tokens':boundary.api.total_tokens,'boltz_calls':boundary.executor.boltz_calls,'admet_calls':boundary.executor.admet_calls,'tool_calls':boundary.tools,'error':boundary.error,'resumed':resume,'started':started,'ended':time.time()}
 except Exception as exc:
  (out/'error.log').write_text(traceback.format_exc());result={'status':'error','error':str(exc),'task':tid,'method':'solpi'}
 finally:server.shutdown()
 dump(out/'result.json',result);print(json.dumps(result),flush=True);return result

if __name__=='__main__':job(sys.argv[1],'--smoke' in sys.argv,'--resume' in sys.argv)
