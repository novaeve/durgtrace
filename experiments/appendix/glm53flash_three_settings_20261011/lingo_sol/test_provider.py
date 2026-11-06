"""Offline tests for native caps, selection, and full streamed tool arguments."""
import copy,importlib.util,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/data2/chenfuxin/chatdrug_generalization_20260920');sys.path.insert(0,str(ROOT))
import provider,lingo_relay
sys.path.insert(0,str(ROOT/'sol_pi'))
import relay as sol
fake={'base':'https://tok.fan/v1','key':'OFFLINE_SENTINEL_NEVER_LOG'}
class Answer:
 status_code=200
 def close(self):pass
 def json(self):return {'model':'glm-5.3-flash','choices':[{'message':{'content':'CCO'},'finish_reason':'stop'}],'usage':{}}
class Session:
 def __init__(self):self.bodies=[]
 def close(self):pass
 def post(self,url,**kwargs):self.bodies.append(copy.deepcopy(kwargs['json']));return Answer()
with tempfile.TemporaryDirectory(dir=ROOT) as d:
 with patch.object(provider,'config',return_value=fake),patch.object(provider.requests,'Session',Session):
  ll=lingo_relay.Relay(Path(d)/'api.json')
  assert ll.complete([{'role':'user','content':'molecular task'}],'block_substitution')=='CCO'
  body=ll.session.bodies[0]
  assert body['reasoning_effort']=='low' and 'max_completion_tokens' not in body
  assert fake['key'] not in (Path(d)/'api.json').read_text()
 original={'model':'old','messages':[{'role':'system','content':'native chemistry tools'},{'role':'user','content':'task'}],
  'tools':[{'type':'function','function':{'name':'bash','parameters':{'type':'object','properties':{'command':{'type':'string'}}}}}],
  'max_tokens':65536,'enable_thinking':False}
 payload=sol.settings(original)
 assert payload['messages']==original['messages'] and payload['tools']==original['tools']
 assert payload['model']=='glm-5.3-flash' and payload['reasoning_effort']=='low'
 assert 'max_tokens' not in payload and 'max_completion_tokens' not in payload and 'enable_thinking' not in payload
 def chunks(finish):
  return [{'id':'offline','model':'glm-5.3-flash','choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'id':'tool_1','function':{'name':'bash','arguments':'{"command":'}}]}}]},
   {'model':'glm-5.3-flash','choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"python -V"}'}}]},'finish_reason':finish}]}]
 class Stream:
  status_code=200
  def __init__(self,finish):self.finish=finish
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def iter_lines(self,**kwargs):
   for c in chunks(self.finish):yield b'data: '+json.dumps(c).encode()
   yield b'data: [DONE]'
 with patch.object(sol.frozen,'load_credentials',return_value={'base_url':fake['base'],'api_key':fake['key']}):
  rr=sol.Relay(Path(d)/'sol')
  with patch.object(sol.requests,'post',return_value=Stream('tool_calls')):
   result,lines=rr.complete(original)
   assert json.loads(result['choices'][0]['message']['tool_calls'][0]['function']['arguments'])=={'command':'python -V'}
   assert rr.truncations==0
  with patch.object(sol.requests,'post',return_value=Stream('length')):
   try:rr.complete(original)
   except RuntimeError as exc:assert 'truncated' in str(exc)
   else:raise AssertionError('Truncated tool calls must never be forwarded')
   assert rr.truncations==1
  assert all(fake['key'] not in p.read_text() for p in (Path(d)/'sol/api').glob('*.json'))
print('PROVIDER_NATIVE_CAPS_AND_TOOL_STREAM_CHECK_PASSED',flush=True)
