import json,pathlib,time
from urllib.parse import urlsplit
import requests
import runner as r

MODEL='deepseek-v4.1-flash'
def config():
 values={}
 for line in (r.ROOT/'private/deepseek_canchen.env').read_text(encoding='utf-8-sig').splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1);values[k.strip().lower()]=v.strip().strip('"').strip("'")
 parsed=urlsplit(values['base_url'])
 assert parsed.scheme=='https' and parsed.hostname.endswith('.aliyuncs.com')
 return values

class Relay:
 def __init__(self,path):
  self.path=path;self.calls=[];self.config=config();self.session=requests.Session()
 def complete(self,messages,label,max_tokens=None):
  body={'model':MODEL,'messages':messages,'temperature':0,'stream':False,'enable_thinking':False}
  record={'label':label,'requested_model':MODEL,'messages':messages,'provider':'Alibaba Bailian','request_settings':{'temperature':0,'max_tokens':None,'cap_policy':'provider default','enable_thinking':False},'attempts':[]}
  self.calls.append(record)
  for attempt in range(3):
   start=time.monotonic()
   try:
    response=self.session.post(self.config['base_url'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+self.config['api_key'],'Content-Type':'application/json'},json=body,timeout=(20,180))
    record['attempts'].append({'attempt':attempt+1,'status':response.status_code,'seconds':round(time.monotonic()-start,3)})
    if response.status_code!=200:
     if response.status_code in [408,429,500,502,503,504] and attempt<2:
      response.close();time.sleep(2**attempt*2);continue
     try:
      err=response.json().get('error',{});detail=json.dumps(err,ensure_ascii=False)
      for v in self.config.values():detail=detail.replace(v,'[redacted]')
      record['error_detail']=detail[:500]
     except ValueError:pass
     status=response.status_code;response.close();r.dump(self.path,self.calls);raise r.p.RelayError('HTTP_'+str(status))
    data=response.json();response.close();choices=data.get('choices',[])
    if not choices:
     r.dump(self.path,self.calls);raise r.p.RelayError('NO_CHOICES')
    choice=choices[0];message=choice.get('message',{});text=message.get('content') or '';usage=data.get('usage',{})
    stop=choice.get('finish_reason');record.update(response_model=data.get('model'),output=text,stop_reason='max_tokens' if stop=='length' else stop,reasoning_present=bool(message.get('reasoning_content')),raw_usage=usage,usage={'input_tokens':usage.get('prompt_tokens',0),'output_tokens':usage.get('completion_tokens',0),'cache_read_input_tokens':usage.get('prompt_tokens_details',{}).get('cached_tokens',0)})
    r.dump(self.path,self.calls)
    if stop=='length':raise r.p.RelayError('OUTPUT_TRUNCATED')
    if not text:raise r.p.RelayError('NO_TEXT_BLOCK')
    return text
   except requests.RequestException as e:
    record['attempts'].append({'attempt':attempt+1,'error_type':type(e).__name__});r.dump(self.path,self.calls)
    if attempt<2:time.sleep(2**attempt*2);continue
    raise r.p.RelayError('TRANSPORT_ERROR') from None

if __name__=='__main__':
 relay=Relay(r.ROOT/'runs/bailian_probe/api_calls.json')
 text=relay.complete([{'role':'user','content':'Reply with exactly OK.'}],'connectivity')
 assert text.strip()=='OK', 'Unexpected probe response'
 print(json.dumps({'probe':'OK','model':relay.calls[-1]['response_model'],'reasoning_present':relay.calls[-1]['reasoning_present'],'usage':relay.calls[-1]['usage']}))
