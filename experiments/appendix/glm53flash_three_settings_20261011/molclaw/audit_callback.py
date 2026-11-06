"""Minimal per-case provider receipts; never persist keys, headers or message content."""
import hashlib,json,re,time,uuid
from pathlib import Path
from litellm.integrations.custom_logger import CustomLogger
ROOT=Path(__file__).resolve().parent
MODEL='glm-5.3-flash'
def case_label(value,depth=0):
 if depth>7:return None
 if isinstance(value,dict):
  for k,v in value.items():
   if str(k).lower()=='x-molclaw-case' and isinstance(v,str) and re.fullmatch(r'(?:1_original_chatdrug|2_s2_prompt_chatdrug|3_original_s2)/(?:source_\d+_(?:loose|strict)_\d+|s2_(?:LogP|QED)_\d+)',v):return v
  for v in value.values():
   if isinstance(v,(dict,list)):
    answer=case_label(v,depth+1)
    if answer:return answer
 elif isinstance(value,list):
  for v in value:
   if isinstance(v,(dict,list)):
    answer=case_label(v,depth+1)
    if answer:return answer
 return None
def simple_response(response):
 if hasattr(response,'model_dump'):return response.model_dump()
 return response if isinstance(response,dict) else {}
def save(kwargs,response,status):
 obj=simple_response(response)
 full=kwargs.get('complete_streaming_response')
 if full:obj=simple_response(full)
 label=case_label(kwargs) or '_unassigned'
 lp=kwargs.get('litellm_params') or {};opt=kwargs.get('optional_params') or {}
 extra=lp.get('extra_body') or opt.get('extra_body') or {}
 model=obj.get('model')
 row={'status':status,'case':label,'model_requested':kwargs.get('model'),'response_model':model,'time':time.time(),
  'response_model_ok':model==MODEL or bool(re.fullmatch(re.escape(MODEL)+r'-\d{4}-\d{2}-\d{2}',str(model))),
  'settings':{k:opt.get(k,kwargs.get(k)) for k in ('temperature','max_tokens','max_completion_tokens','reasoning_effort','stream')},
  'extra_reasoning_effort':extra.get('reasoning_effort'),'usage':{k:v for k,v in (obj.get('usage') or {}).items() if isinstance(v,(int,float))},
  'finish_reason':[(c or {}).get('finish_reason') for c in obj.get('choices',[]) if isinstance(c,dict)]}
 if status=='error':
  exc=kwargs.get('exception');row['error_type']=type(exc).__name__ if exc else type(response).__name__
  row['status_code']=getattr(exc,'status_code',None)
 path=ROOT/'proxy_audit'/label/(str(uuid.uuid4())+'.json')
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(row,indent=2));tmp.replace(path)
class AuditLogger(CustomLogger):
 async def async_log_success_event(self,kwargs,response_obj,start_time,end_time):save(kwargs,response_obj,'complete')
 async def async_log_failure_event(self,kwargs,response_obj,start_time,end_time):save(kwargs,response_obj,'error')
audit_logger=AuditLogger()
