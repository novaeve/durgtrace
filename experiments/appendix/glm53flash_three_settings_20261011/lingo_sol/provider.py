"""GPT-6 Luna adapter for frozen native agent runners; messages and caps unchanged."""
import copy,json,re,time
from pathlib import Path
from urllib.parse import urlsplit
import requests
from pilot import RelayError
ROOT=Path(__file__).resolve().parent
MODEL='glm-5.3-flash'
def config():
    return {'base':'http://127.0.0.1:18853/v4','key':'local-glm-boundary'}
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2));temp.replace(path)
def compatible(returned):
    return returned==MODEL or bool(re.fullmatch(re.escape(MODEL)+r'-\d{4}-\d{2}-\d{2}',str(returned)))
def catalog():
    cfg=config()
    for attempt in range(6):
        try:
            response=requests.get(cfg['base']+'/models',headers={'Authorization':'Bearer '+cfg['key']},
                                  timeout=(20,45),allow_redirects=False)
            status=response.status_code
            if status==200:
                ids=[x['id'] for x in response.json().get('data',[]) if 'id' in x]
                response.close();assert MODEL in ids
                return {'model':MODEL,'available':True,'checked':time.time(),'host':'open.bigmodel.cn via isolated local gateway'}
            response.close()
            if status not in (408,429,500,502,503,504):raise RelayError('CATALOG_HTTP_'+str(status))
        except requests.RequestException:
            if attempt==5:raise RelayError('CATALOG_TRANSPORT_ERROR') from None
        time.sleep(min(5*2**attempt,30))
    raise RelayError('CATALOG_RETRY_EXHAUSTED')
class Relay:
    def __init__(self,path):
        self.log_path=Path(path);self.calls=[];self.config=config();self.session=requests.Session();self.replay=[]
        previous=json.loads(self.log_path.read_text()) if self.log_path.exists() else []
        for call in previous:
            if 'output' in call and call.get('response_model') and call.get('error') in (None,'OUTPUT_TRUNCATED'):
                self.replay.append(copy.deepcopy(call))
            else:break
    def save(self):dump(self.log_path,self.calls)
    def complete(self,messages,label,max_tokens=2048):
        if self.replay:
            cached=self.replay.pop(0)
            assert cached['messages']==messages and cached['label']==label
            assert cached['requested_model']==MODEL and cached['request_settings']['max_tokens']==max_tokens
            self.calls.append(cached);self.save()
            if cached.get('stop_reason')=='max_tokens':raise RelayError('OUTPUT_TRUNCATED')
            return cached['output']
        immutable=copy.deepcopy(messages)
        body={'model':MODEL,'messages':immutable,'temperature':0,'reasoning_effort':'low','stream':False,'n':1}
        if max_tokens is not None:body['max_completion_tokens']=max_tokens
        record={'label':label,'requested_model':MODEL,'messages':copy.deepcopy(messages),'provider':'open.bigmodel.cn via isolated local gateway',
                'request_settings':{'temperature':0,'max_tokens':max_tokens,'reasoning_effort':'low'},'attempts':[]}
        self.calls.append(record)
        for attempt in range(6):
            start=time.monotonic()
            try:
                response=self.session.post(self.config['base']+'/chat/completions',json=body,
                    headers={'Authorization':'Bearer '+self.config['key']},timeout=(20,180),allow_redirects=False)
                status=response.status_code
                entry={'attempt':attempt+1,'status':status,'seconds':round(time.monotonic()-start,3)}
                record['attempts'].append(entry)
                if status!=200:
                    try:
                        error=response.json().get('error',{})
                        detail=json.dumps(error,ensure_ascii=False).replace(self.config['key'],'[REDACTED]')
                        entry['error_detail']=detail[:800]
                        error_code=error.get('code') if isinstance(error,dict) else None
                    except ValueError:error_code=None
                    response.close();self.save()
                    retry=status in (408,429,500,502,503,504,529) or (status==404 and error_code=='model_not_found')
                    if retry and attempt<5:time.sleep(min(5*2**attempt,30));continue
                    raise RelayError('HTTP_'+str(status))
                try:data=response.json()
                finally:response.close()
                choices=data.get('choices') or []
                if len(choices)!=1:raise RelayError('NO_CHOICES')
                if not compatible(data.get('model')):raise RelayError('RETURNED_MODEL_MISMATCH')
                choice=choices[0];message=choice.get('message',{});text=message.get('content') or ''
                if not isinstance(text,str):raise RelayError('UNEXPECTED_OUTPUT_TYPE')
                stop=choice.get('finish_reason');usage=data.get('usage',{})
                text=text.replace(self.config['key'],'[REDACTED]')
                record.update(response_model=data.get('model'),output=text,
                    stop_reason='max_tokens' if stop=='length' else ('refusal' if message.get('refusal') else stop),
                    raw_usage=usage,reasoning_present=bool(usage.get('completion_tokens_details',{}).get('reasoning_tokens')),
                    usage={'input_tokens':usage.get('prompt_tokens',0),'output_tokens':usage.get('completion_tokens',0),
                           'cache_read_input_tokens':usage.get('prompt_tokens_details',{}).get('cached_tokens',0)})
                self.save()
                if stop=='length':raise RelayError('OUTPUT_TRUNCATED')
                if message.get('refusal'):return ''
                if not text:raise RelayError('NO_TEXT_BLOCK')
                return text
            except (requests.RequestException,ValueError) as exc:
                record['attempts'].append({'attempt':attempt+1,'error_type':type(exc).__name__,'seconds':round(time.monotonic()-start,3)})
                self.session.close();self.session=requests.Session();self.save()
                if attempt<5:time.sleep(min(5*2**attempt,30));continue
                record['error']='TRANSPORT_ERROR';self.save();raise RelayError('TRANSPORT_ERROR') from None
            except RelayError as exc:
                record['error']=str(exc);self.save()
                if str(exc) in ('NO_CHOICES','NO_TEXT_BLOCK') and attempt<5:
                    time.sleep(min(5*2**attempt,30));continue
                raise
        raise RelayError('RETRY_EXHAUSTED')
