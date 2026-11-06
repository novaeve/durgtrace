"""Fault recovery preserves completed science, recovers cached replies and verifies the provider."""
import ast,collections,hashlib,io,json,tempfile,threading,time
from pathlib import Path
from resilience_common import read,write,recoverable,repair_idle_codex,repair_idle_direct

with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent,prefix='resilience_fixture_') as directory:
 root=Path(directory);codex=root/'codex';jobs=[];pinned={}
 records=[('valid_failure',{'status':'complete','score':{'success':False}}),
          ('native_timeout',{'status':'timeout','retryable':True}),
          ('token_cap',{'status':'provider_limit'}),
          ('refusal',{'status':'error','retryable':False,'error':'Provider finish_reason: sensitive'}),
          ('network',{'status':'error','retryable':True,'error':'gateway_timeout'})]
 for ident,row in records:
  job={'setting':'test','case':{'id':ident}};jobs.append(job)
  path=codex/'runs/Codex/test'/ident/'result.json';write(path,row)
  if ident!='network':pinned[path]=hashlib.sha256(path.read_bytes()).hexdigest()
 jobs.append({'setting':'test','case':{'id':'unfinished'}})
 write(codex/'native/runs/test/unfinished/started.json',{'started':1})
 write(codex/'jobs.json',jobs)
 repaired=repair_idle_codex(root)
 assert {x['id'] for x in repaired}=={'network','unfinished'}
 for path,digest in pinned.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
 retry=root/'direct/uncapped_retry1120';write(retry/'jobs.json',[{'setting':'test','case':{'id':'cached'}},{'setting':'test','case':{'id':'unknown_network'}}])
 write(retry/'runs/GLM_direct/test/cached/api.json',{'response':{'model':'glm-5.3-flash','choices':[]}})
 cached=retry/'runs/GLM_direct/test/cached/api.json';digest=hashlib.sha256(cached.read_bytes()).hexdigest()
 write(retry/'runs/GLM_direct/test/unknown_network/transport_error_1.json',{'outcome_unknown':True,'error':'Connection reset'})
 repair_idle_direct(root)
 assert hashlib.sha256(cached.read_bytes()).hexdigest()==digest
 assert not (retry/'runs/GLM_direct/test/unknown_network/transport_error_1.json').exists()

# A circuit is never cleared by authentication failure or a different model.
node=next(n for n in ast.parse(Path(__file__).with_name('gateway_relay_v2.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='recovery_probe')
class Sink:
 def __truediv__(self,key):return self
 def open(self,*args):return io.StringIO()
class Response:
 def __init__(self,status,model):self.status_code=status;self.model=model
 def json(self):return {'model':self.model,'choices':[{'message':{'content':'OK'}}]}
 def close(self):pass
class FakeRequests:
 class RequestException(Exception):pass
 def __init__(self,responses):self.responses=iter(responses)
 def post(self,*args,**kwargs):return next(self.responses)
ns={'condition':threading.Condition(),'time':time,'stats':collections.Counter(),'halted':'Provider unavailable',
    'halted_since':1,'next_recovery_probe':0,'last_recovery':None,'save':lambda:None,
    'MODEL':'glm-5.3-flash','BASE':'http://fixture.invalid','KEY':'fixture-key','PORT':18853,'ROOT':Sink(),
    'json':json,'canonicalize_model':lambda obj,body,seen:obj}
exec(compile(ast.Module(body=[node],type_ignores=[]),'recovery_probe_fixture','exec'),ns)
for responses in ([Response(401,'glm-5.3-flash')],[Response(200,'deepseek-v4.1-flash')]):
 ns['requests']=FakeRequests(responses);ns['next_recovery_probe']=0;ns['recovery_probe']();assert ns['halted']=='Provider unavailable'
ns['requests']=FakeRequests([Response(200,'glm-5.3-flash'),Response(200,'glm-5.3-flash')]);ns['next_recovery_probe']=0
ns['recovery_probe']();assert ns['halted'] is None and ns['stats']['provider_auto_recoveries']==1
print('Recovery checks passed: only unfinished transport cases reset; scientific outcomes and cached replies unchanged; auth/wrong-model failures remain protected; verified GLM recovery resumes.')
