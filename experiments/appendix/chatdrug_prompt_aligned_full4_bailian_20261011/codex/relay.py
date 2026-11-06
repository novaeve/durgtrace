"""Buffered provider transport with bounded transient retries and truthful HTTP error statuses."""
from pathlib import Path
import http.server,json,threading,time,requests
from legacy_relay import MODEL,CREDENTIAL_SOURCE,load_credentials,settings,assemble,guard
from adaptive_gate import STATE
from loop_control import LoopControl,VERSION
MAX_ATTEMPTS=5
class ProviderError(RuntimeError):
 def __init__(self,message,status=400,retryable=False,retry_after=0):
  super().__init__(message);self.status=status;self.retryable=retryable;self.retry_after=retry_after
def failure(message,http_status,detail='',retry_after=0):
 text=str(detail).lower()
 if 'data_inspection_failed' in text:return ProviderError(message,400,False)
 if http_status==429 or 'throttling.' in text:return ProviderError(message,429,True,retry_after)
 if http_status in (408,500,502,503,504):return ProviderError(message,http_status,True,retry_after)
 if http_status==200:return ProviderError(message,502,True,retry_after)
 return ProviderError(message,http_status,False)
class Relay:
 def __init__(self,out):
  self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
  self.credentials=load_credentials();self.lock=threading.Lock();self.calls=0;self.truncations=0;self.loop_control=LoopControl(self.out)
 def record(self,path,value):
  path.parent.mkdir(parents=True,exist_ok=True)
  temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2));temp.replace(path)
 def redact(self,value):return str(value).replace(self.credentials['api_key'],'[REDACTED]')[:1500]
 def complete(self,body):
  with self.lock:self.calls+=1;number=self.calls
  guarded,loop_notice=self.loop_control.apply(body)
  payload=settings(guarded)
  record={'request':payload,'started':time.time(),'attempts':[],'settings':{
   'model':MODEL,'temperature':0,'enable_thinking':False,'reasoning_effort':None,
   'max_tokens':None,'stream':True,'credential_source':str(CREDENTIAL_SOURCE)}}
  record['harness_variant']=VERSION
  record['loop_control']=loop_notice
  path=self.out/'api'/f'{number:06d}.json'
  self.record(path,record)
  try:
   for attempt in range(MAX_ATTEMPTS):
    item={'attempt':attempt+1,'started':time.time()}
    try:
     with STATE.acquire():
      chunks=[];lines=[]
      with requests.post(self.credentials['base_url'].rstrip('/')+'/chat/completions',
       json=payload,headers={'Authorization':'Bearer '+self.credentials['api_key']},
       stream=True,timeout=(30,300)) as response:
       record['http_status']=item['http_status']=response.status_code
       try:retry_after=float(response.headers.get('Retry-After',0))
       except ValueError:retry_after=0
       if response.status_code!=200:
        detail=self.redact(response.text);item['upstream_error']=record['upstream_error']=detail
        raise failure('upstream_http_'+str(response.status_code),response.status_code,detail,retry_after)
       for line in response.iter_lines(chunk_size=4096):
        if not line:continue
        lines.append(line)
        if line.startswith(b'data: ') and line!=b'data: [DONE]':
         chunk=json.loads(line[6:])
         if chunk.get('error'):
          detail=self.redact(json.dumps(chunk['error']))
          item['upstream_error']=record['upstream_error']=detail
          raise failure('upstream_stream_error',200,detail,retry_after)
         if chunk.get('model') and chunk['model']!=MODEL:raise ProviderError('provider_model_mismatch',400,False)
         chunks.append(chunk)
      result=assemble(chunks);record['response']=result
      if result['model']!=MODEL:raise ProviderError('provider_model_mismatch',400,False)
      if result['choices'][0]['finish_reason'] is None:raise ProviderError('incomplete_provider_stream',502,True)
      if result['choices'][0]['finish_reason']=='length':
       with self.lock:self.truncations+=1
       raise ProviderError('Provider output truncated; no truncated tool call executed',400,False)
     item['ended']=time.time();item['success']=True;record['attempts'].append(item)
     record.pop('error',None);record.pop('error_status',None)
     STATE.success()
     return result,lines
    except (requests.RequestException,ValueError) as exc:
     problem=ProviderError(type(exc).__name__,503,True)
    except ProviderError as exc:problem=exc
    item.update(error=str(problem),error_status=problem.status,ended=time.time())
    record['attempts'].append(item);record['error']=str(problem);record['error_status']=problem.status
    delay=STATE.throttle(problem.retry_after) if problem.status==429 else min(30,2**(attempt+1))
    if not problem.retryable or attempt+1==MAX_ATTEMPTS:raise problem
    item['retry_backoff_seconds']=delay
    self.record(path,record)
    if problem.status!=429:time.sleep(delay)
   raise ProviderError('retry_budget_exhausted',503,True)
  finally:
   record['ended']=time.time();self.record(path,record)
 def service(self):
  state=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def send(self,obj,status=200,retry_after=None):
    raw=json.dumps(obj).encode();self.send_response(status)
    self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
    if retry_after:self.send_header('Retry-After',str(int(retry_after)))
    self.end_headers();self.wfile.write(raw)
   def do_POST(self):
    try:
     body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
     if self.path=='/guard':self.send({'reason':guard(body['name'],body.get('input') or {})});return
     if self.path!='/v1/chat/completions':self.send({'error':{'message':'Unknown endpoint'}},404);return
     result,lines=state.complete(body)
     if not body.get('stream'):self.send(result);return
     self.send_response(200);self.send_header('Content-Type','text/event-stream')
     self.send_header('Connection','close');self.end_headers()
     for line in lines:self.wfile.write(line+b'\n\n')
     if not any(line==b'data: [DONE]' for line in lines):self.wfile.write(b'data: [DONE]\n\n')
     self.wfile.flush();self.close_connection=True
    except (BrokenPipeError,ConnectionResetError):pass
    except Exception as exc:
     status=exc.status if isinstance(exc,ProviderError) else 500
     message=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
     try:self.send({'error':{'message':message,'code':str(status)}},status,10 if status==429 else None)
     except OSError:pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
  server.daemon_threads=True;threading.Thread(target=server.serve_forever,daemon=True).start()
  return server

