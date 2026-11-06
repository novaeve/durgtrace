from pathlib import Path
import hashlib,http.server,json,os,subprocess,threading,time,traceback,uuid
import requests
from oracle_server import OracleService,LEGACY
from pmo_common import Relay,dump,append
from guard import python_reason

class Boundary:
    def __init__(self,out,work,task,budget):
        self.out,self.work=out,work;self.oracle=OracleService(out,task,budget)
        self.config=Relay(out).config;self.calls=len(list((out/'api').glob('*.json')))
        self.api_lock=threading.Lock();self.tools_lock=threading.Lock();self.truncations=json.loads((out/'truncation_state.json').read_text()).get('count',0) if (out/'truncation_state.json').exists() else 0;self.error=None
    def python(self,code):
        reason=python_reason(code)
        if reason:return {'error':reason}
        for f in self.work.glob('*.py'):
            issue=python_reason(f.read_text())
            if issue:return {'error':'Workspace helper '+f.name+': '+issue}
        script=self.work/('pmo_tmp_'+uuid.uuid4().hex+'.py');script.write_text(code)
        cmd=['bwrap','--unshare-all','--die-with-parent','--new-session']
        for p in ['/usr','/bin','/lib','/lib64','/etc']:cmd+=['--ro-bind',p,p]
        cmd+=['--ro-bind',str(LEGACY/'venv'),str(LEGACY/'venv'),'--proc','/proc','--dev','/dev','--tmpfs','/tmp','--bind',str(self.work),'/workspace','--chdir','/workspace','--clearenv','--setenv','PATH',str(LEGACY/'venv/bin')+':/usr/bin:/bin','--setenv','HOME','/tmp','--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1',str(LEGACY/'venv/bin/python'),'/workspace/'+script.name]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
            return {'output':(p.stdout+p.stderr)[:16000],'exit_code':p.returncode}
        finally:script.unlink(missing_ok=True)
    def call(self,name,args):
        if name=='python':return self.python(args['code'])
        if name in ['score_molecules','score_file']:
            if name=='score_file':
                path=(self.work/args['file_path'].removeprefix('/workspace/')).resolve()
                if not path.is_relative_to(self.work.resolve()):raise ValueError('File must be inside workspace')
                molecules=path.read_text().splitlines()
            else:molecules=args['smiles']
            result=self.oracle.score(molecules,'native_codex_'+name)
            dump(self.work/'latest_scores.json',result)
            return result
        if name=='budget_status':
            ledger=self.oracle.ledger()
            return {'used':len(ledger.rows),'remaining':ledger.budget-len(ledger.rows),'budget':ledger.budget,'top10':[{'smiles':s,'score':v[0]} for s,v in sorted(ledger.buffer.items(),key=lambda x:-x[1][0])[:10]]}
        raise ValueError('Unknown tool')
    def complete(self,body):
        self.calls+=1
        payload={'model':'deepseek-v4.1-flash','messages':body['messages'],'temperature':0,'enable_thinking':False,'stream':False}
        if body.get('tools'):payload['tools']=body['tools']
        path=self.out/'api'/f'{self.calls:06d}.json';record={'request':payload,'started':time.time(),'attempts':[]}
        for attempt in range(4):
            try:
                response=requests.post(self.config['base_url'].rstrip('/')+'/chat/completions',json=payload,headers={'Authorization':'Bearer '+self.config['api_key']},timeout=(20,180))
                record['attempts'].append({'status':response.status_code,'time':time.time()})
                if response.status_code!=200:
                    dump(path,record)
                    if response.status_code in [408,429,500,502,503,504] and attempt<3:time.sleep(2**attempt*2);continue
                    raise RuntimeError('API HTTP '+str(response.status_code))
                data=response.json();record.update(response=data,ended=time.time());dump(path,record)
                if data.get('model')!='deepseek-v4.1-flash':raise RuntimeError('Unexpected response model')
                if data['choices'][0].get('finish_reason')=='length':
                    self.truncations+=1
                    dump(self.out/'truncation_state.json',{'count':self.truncations,'api_call':self.calls,'time':time.time()})
                    raise RuntimeError('Provider output truncated; no truncated tool call executed')
                return data
            except requests.RequestException as exc:
                record['attempts'].append({'error':type(exc).__name__});dump(path,record)
                if attempt==3:raise RuntimeError('API transport retries exhausted') from None
                time.sleep(2**attempt*2)
    def service(self):
        state=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,obj,status=200):
                raw=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):self.send({})
            def do_DELETE(self):self.send({})
            def do_POST(self):
                try:
                    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                    if self.path=='/mcp':
                        rid=body.get('id');method=body.get('method');params=body.get('params',{})
                        if rid is None:self.send_response(202);self.end_headers();return
                        if method=='initialize':result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'pmo-oracle','version':'1'}}
                        elif method=='ping':result={}
                        elif method=='tools/list':
                            result=state.oracle.handle(body)
                            result['tools'] += [
                                {'name':'python','description':'Execute structural generation and validation Python with the shared RDKit environment. No objective/surrogate scoring, fingerprint similarity, network or external programs. Write candidates to a workspace file if useful.','inputSchema':{'type':'object','properties':{'code':{'type':'string'}},'required':['code']}},
                                {'name':'score_file','description':'Submit a workspace text file containing one SMILES per line, in original line order. Each line, including invalid and repeated entries, consumes one oracle submission, until the hard cap. No free screening. Full response saved to latest_scores.json.','inputSchema':{'type':'object','properties':{'file_path':{'type':'string'}},'required':['file_path']}}]
                        elif method=='tools/call':
                            with state.tools_lock:
                                try:
                                    value=state.call(params['name'],params.get('arguments',{}));text=json.dumps(value)
                                    if len(text)>24000:text=text[:24000]+'\n[truncated; full scoring result in latest_scores.json]'
                                    result={'content':[{'type':'text','text':text}],'isError':False}
                                except Exception as exc:result={'content':[{'type':'text','text':type(exc).__name__+': '+str(exc)}],'isError':True}
                                append(state.out/'mcp_receipts.jsonl',{'time':time.time(),'request':body,'result':result})
                        else:self.send({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Unknown method'}});return
                        self.send({'jsonrpc':'2.0','id':rid,'result':result});return
                    if not self.path.split('?')[0].endswith('/chat/completions'):self.send({'error':'Unsupported route'},404);return
                    with state.api_lock:data=state.complete(body)
                    if not body.get('stream'):self.send(data);return
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    delta=dict(data['choices'][0]['message'])
                    if delta.get('tool_calls'):delta['tool_calls']=[dict(t,index=i) for i,t in enumerate(delta['tool_calls'])]
                    chunk={'id':data['id'],'object':'chat.completion.chunk','created':data.get('created',int(time.time())),'model':data['model'],'choices':[{'index':0,'delta':delta,'finish_reason':None}]}
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
                    chunk['choices']=[{'index':0,'delta':{},'finish_reason':data['choices'][0].get('finish_reason','stop')}];chunk['usage']=data.get('usage',{})
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass
                except Exception as exc:
                    state.error=str(exc);dump(state.out/'transport_error.json',{'error':str(exc),'time':time.time()})
                    try:self.send({'error':{'message':str(exc)}},400)
                    except OSError:pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start();return server
