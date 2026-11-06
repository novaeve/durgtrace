"""Native buffered tool-call relay, with GPT provider adaptation only."""
import copy,json,sys,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from provider import config,compatible,MODEL
import frozen_relay as frozen
frozen.MODEL=MODEL
frozen.CREDENTIAL_SOURCE=ROOT/'private/chatgpt.env'
def credentials():
 cfg=config();return {'base_url':cfg['base'],'api_key':cfg['key']}
frozen.load_credentials=credentials
def settings(body):
 payload=copy.deepcopy(body)
 payload.update(model=MODEL,temperature=0,reasoning_effort='low',stream=True)
 for k in ('enable_thinking','reasoning','thinking','max_tokens','max_completion_tokens','store'):
  payload.pop(k,None)
 return payload
frozen.settings=settings
class Relay(frozen.Relay):
 def complete(self,body):
  with self.lock:self.calls+=1;number=self.calls
  payload=settings(body)
  record={'request':payload,'started':time.time(),'settings':{'model':MODEL,'temperature':0,'reasoning_effort':'low','max_tokens':None,'stream':True},'attempts':[]}
  path=self.out/'api'/f'{number:06d}.json';self.record(path,record)
  for attempt in range(6):
   entry={'attempt':attempt+1,'started':time.time()};record['attempts'].append(entry)
   try:
    chunks,lines=[],[]
    with requests.post(self.credentials['base_url'].rstrip('/')+'/chat/completions',
     json=payload,headers={'Authorization':'Bearer '+self.credentials['api_key']},stream=True,
     timeout=(30,300),allow_redirects=False) as response:
     record['http_status']=entry['http_status']=response.status_code
     if response.status_code!=200:
      try:
       obj=response.json().get('error',{});code=obj.get('code') if isinstance(obj,dict) else None
       entry['error_detail']=json.dumps(obj,ensure_ascii=False).replace(self.credentials['api_key'],'[REDACTED]')[:800]
      except ValueError:code=None
      status=response.status_code
      error='upstream_http_'+str(status)
      if status in (408,429,500,502,503,504,529) or (status==404 and code=='model_not_found'):
       raise RuntimeError('transient_'+error)
      raise RuntimeError(error)
     for line in response.iter_lines(chunk_size=4096):
      if not line:continue
      if self.credentials['api_key'].encode() in line:line=line.replace(self.credentials['api_key'].encode(),b'[REDACTED]')
      lines.append(line)
      if line.startswith(b'data: ') and line!=b'data: [DONE]':
       chunk=json.loads(line[6:])
       if chunk.get('error'):raise RuntimeError('upstream_stream_error')
       if chunk.get('model') and not compatible(chunk['model']):raise RuntimeError('provider_model_mismatch')
       chunks.append(chunk)
    result=frozen.assemble(chunks);record['response']=result
    if not compatible(result['model']) or result['choices'][0]['finish_reason'] is None:
     raise RuntimeError('incomplete_provider_stream')
    record.pop('error',None)
    if result['choices'][0]['finish_reason']=='length':
     with self.lock:self.truncations+=1
     raise RuntimeError('Provider output truncated; no truncated tool call executed')
    record['ended']=time.time();self.record(path,record)
    return result,lines
   except Exception as exc:
    error=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
    entry['error']=record['error']=error;record['ended']=time.time();self.record(path,record)
    retry=isinstance(exc,(requests.RequestException,ValueError)) or error.startswith('transient_') or error in ('upstream_stream_error','incomplete_provider_stream')
    if retry and attempt<5:time.sleep(min(5*2**attempt,30));continue
    raise
