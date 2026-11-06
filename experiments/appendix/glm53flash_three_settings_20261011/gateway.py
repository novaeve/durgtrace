"""Shared GLM transport: relay compatibility, strict model checks and adaptive capacity."""
import collections,hashlib,http.server,json,os,re,threading,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent;MODEL='glm-5.3-flash'
PORT=int(os.environ.get('GLM_GATEWAY_PORT','18853'));MAX_LIMIT=96 if PORT==18853 else 16
STATE=ROOT/('gateway_state.json' if PORT==18853 else 'gateway_claw_state.json')
values={}
for line in (ROOT/'private/GLM.env').read_text(encoding='utf-8-sig').splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.strip().removeprefix('export ').split('=',1);values[k.strip().upper()]=v.strip().strip('\"').strip("'")
KEY=values['API_KEY'];BASE=values.get('URL','https://open.bigmodel.cn/api/paas/v4').rstrip('/')
PROVIDER_EPOCH=json.loads((ROOT/'provider_switch.json').read_text()).get('epoch','relay')
condition=threading.Condition();active=0;limit=64 if PORT==18853 else 16
successes=0;last_limit=time.time();stats=collections.Counter();halted=None
def snapshot():return dict(model=MODEL,upstream=BASE,provider_epoch=PROVIDER_EPOCH,max_limit=MAX_LIMIT,active=active,limit=limit,stats=dict(stats),halted=halted,time=time.time())
def save():
 p=STATE.with_suffix('.tmp');p.write_text(json.dumps(snapshot(),indent=2));p.replace(STATE)
def canonicalize_model(obj,body,seen):
 actual=obj.get('model')
 known=(MODEL,'glm-5-3-flash-260828')
 qualified=False
 if isinstance(actual,str) and actual.count('/')==1:
  namespace,identifier=actual.split('/',1)
  qualified=bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}',namespace) and identifier in known)
 if actual=='glm-5-3-flash-260828' or qualified:
  # A provider namespace does not change the exact model identifier; keep the raw label.
  obj['_experiment_upstream_model']=actual;obj['_experiment_model_alias_applied']=True
  obj['model']=MODEL
  if actual not in seen:
   seen.add(actual)
   entry={'requested_model':body['model'],'upstream_model':actual,'client_model':MODEL,
    'response_id':obj.get('id'),'upstream':BASE,'epoch':PROVIDER_EPOCH,'time':time.time(),
    'messages_sha256':hashlib.sha256(json.dumps(body['messages'],sort_keys=True).encode()).hexdigest()}
   with (ROOT/'model_alias_audit.jsonl').open('a') as f:f.write(json.dumps(entry)+'\n')
   with condition:stats['model_alias_responses']+=1
 return obj

class StreamModelGuard:
 """Inherit model metadata only after this same completion explicitly verifies GLM."""
 def __init__(self,normalize):
  self.normalize=normalize;self.verified=None;self.pending=[];self.pending_bytes=0
 def inherit(self,obj):
  obj['model']=MODEL;obj['_experiment_upstream_model']=None
  obj['_experiment_verified_upstream_model']=self.verified
  obj['_experiment_model_metadata_inherited']=True
  return obj
 def push(self,obj):
  if not isinstance(obj,dict):raise ValueError('Invalid upstream stream object')
  obj=self.normalize(obj);actual=obj.get('model')
  if actual==MODEL:
   self.verified=obj.get('_experiment_upstream_model') or actual
   frames=[self.inherit(p) for p in self.pending]+[obj]
   self.pending=[];self.pending_bytes=0;return frames
  if actual:raise ValueError('Upstream stream model mismatch: '+str(actual))
  if self.verified:return [self.inherit(obj)]
  self.pending.append(obj);self.pending_bytes+=len(json.dumps(obj))
  if self.pending_bytes>8*1024*1024:raise ValueError('Unverified upstream stream exceeds buffer limit')
  return []
 def finish(self):
  if not self.verified:raise ValueError('No verified GLM model frame')

def failure(status,data):
 global limit,successes,last_limit,halted
 data=json.loads(json.dumps(data).replace(KEY,'[REDACTED]'))
 error=data.get('error',{}) if isinstance(data,dict) else {}
 if not isinstance(error,dict):error={'message':str(error)}
 code=str(error.get('code',''));message=str(error.get('message',''))
 if code=='429' or any(s in message.lower() for s in ('too many requests','concurrency limit','rate limit')):status=429
 with condition:
  stats['provider_failures']+=1
  if status==429:limit=max(8,int(limit*.75));successes=0;last_limit=time.time()
  if status in (401,403) or code in ('1113','1002','1003','1004','insufficient_quota'):
   halted='Selected provider rejected credentials, permission or balance: '+code
  save()
 with (ROOT/'relay_transport_errors.jsonl').open('a') as f:
  f.write(json.dumps({'port':PORT,'status':status,'error':error,'time':time.time()})+'\n')
 return status,data
class Handler(http.server.BaseHTTPRequestHandler):
 protocol_version='HTTP/1.0'
 def log_message(self,*args):pass
 def reply(self,status,data):
  raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  if self.path in ('/health','/health/liveliness'):return self.reply(200,snapshot())
  if self.path.endswith('/models'):return self.reply(200,{'object':'list','data':[{'id':MODEL,'object':'model','owned_by':'selected-provider'}]})
  return self.reply(404,{'error':'unknown_route'})
 def do_POST(self):
  global active,successes,last_limit,limit,halted
  if not self.path.split('?',1)[0].endswith('/chat/completions'):return self.reply(404,{'error':'unknown_route'})
  try:body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  except Exception:return self.reply(400,{'error':'invalid_json'})
  if body.get('model') not in (MODEL,'openai/'+MODEL):return self.reply(400,{'error':'unexpected_model'})
  body['model']=MODEL;body['reasoning_effort']='low'
  for key in ('thinking','enable_thinking','reasoning','store','prompt_cache_key'):body.pop(key,None)
  if 'max_completion_tokens' in body:body['max_tokens']=body.pop('max_completion_tokens')
  with condition:
   while active>=limit and not halted:condition.wait(2)
   if halted:return self.reply(503,{'error':{'code':'EXPERIMENT_HALTED','message':halted}})
   active+=1;stats['requests']+=1;save()
  response=None;headers_sent=False;seen_models=set()
  try:
   response=requests.post(BASE+'/chat/completions',json=body,headers={'Authorization':'Bearer '+KEY},stream=bool(body.get('stream')),timeout=(20,600),allow_redirects=False)
   with condition:stats['http_'+str(response.status_code)]+=1
   if response.status_code!=200:
    try:data=response.json()
    except ValueError:data={'error':{'code':str(response.status_code),'message':'upstream_non_json'}}
    status,data=failure(response.status_code,data);return self.reply(status,data)
   streamed=body.get('stream') and 'text/event-stream' in response.headers.get('Content-Type','')
   if streamed:
    guard=StreamModelGuard(lambda obj:canonicalize_model(obj,body,seen_models));inheritance_logged=False
    for line in response.iter_lines(chunk_size=1024):
     if not line or not line.startswith(b'data:'):continue
     raw=line[5:].strip()
     if raw==b'[DONE]':
      guard.finish()
      if headers_sent:self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
      break
     try:obj=json.loads(raw)
     except ValueError:raise ValueError('Invalid upstream stream JSON')
     if obj.get('error'):
      status,obj=failure(502,obj)
      if not headers_sent:return self.reply(status,obj)
      raise ValueError('Upstream stream returned an error after headers')
     for frame in guard.push(obj):
      if frame.get('_experiment_model_metadata_inherited') and not inheritance_logged:
       inheritance_logged=True
       entry={'verified_upstream_model':guard.verified,'upstream_model_field_missing':True,
        'response_id':frame.get('id'),'upstream':BASE,'epoch':PROVIDER_EPOCH,'time':time.time(),
        'messages_sha256':hashlib.sha256(json.dumps(body['messages'],sort_keys=True).encode()).hexdigest()}
       with (ROOT/'stream_model_metadata_audit.jsonl').open('a') as f:f.write(json.dumps(entry)+'\n')
       with condition:stats['stream_metadata_inherited_responses']+=1
      if not headers_sent:
       self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();headers_sent=True
      self.wfile.write(b'data: '+json.dumps(frame).encode()+b'\n\n');self.wfile.flush()
      with condition:
       for key in ('prompt_tokens','completion_tokens','total_tokens'):stats[key]+=((frame.get('usage') or {}).get(key) or 0)
    guard.finish()
   else:
    try:obj=response.json()
    except ValueError:raise ValueError('Invalid upstream completion JSON')
    if obj.get('error'):
     status,obj=failure(502,obj);return self.reply(status,obj)
    obj=canonicalize_model(obj,body,seen_models)
    if obj.get('model')!=MODEL:raise ValueError('Upstream completion model mismatch: '+str(obj.get('model')))
    if not obj.get('choices'):raise ValueError('Upstream returned no choices')
    # Keep the exact original model response; do not invent or regenerate answers.
    self.reply(200,obj);headers_sent=True
    with condition:
     for key in ('prompt_tokens','completion_tokens','total_tokens'):stats[key]+=((obj.get('usage') or {}).get(key) or 0)
   with condition:
    successes+=1
    if successes>=100 and time.time()-last_limit>60 and limit<MAX_LIMIT:
     limit=min(MAX_LIMIT,limit+4);successes=0;last_limit=time.time()
  except (BrokenPipeError,ConnectionResetError):
   with condition:stats['disconnected']+=1
  except (requests.RequestException,ValueError) as error:
   detail=str(error).replace(KEY,'[REDACTED]')
   if 'model mismatch' in detail:
    with condition:halted=detail
   status,data=failure(502,{'error':{'code':'TRANSPORT_ERROR','message':detail}})
   if not headers_sent:
    try:self.reply(status,data)
    except OSError:pass
  finally:
   if response is not None:response.close()
   with condition:active-=1;save();condition.notify_all()
if __name__=='__main__':
 os.chmod(ROOT/'private/GLM.env',0o600);save()
 http.server.ThreadingHTTPServer.request_queue_size=256
 print('RELAY_GATEWAY_READY '+str(PORT),flush=True)
 http.server.ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
