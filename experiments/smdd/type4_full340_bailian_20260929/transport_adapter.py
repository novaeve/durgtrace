import json,subprocess,types,time
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20','-o','ServerAliveInterval=30','-i','/home/chenfuxin/.ssh/smdd_gpu2','-p','17065','chenfuxin@123.157.219.189']
REMOTE='/data2/chenfuxin/smdd_type4_full340_bailian_20260929/llm_gpu.py'
def request(messages,tools=None,temperature=0,max_tokens=None):
 body={'messages':[{k:v for k,v in m.items() if k!='cache_control'} for m in messages],'temperature':temperature}
 if tools:body['tools']=tools
 if max_tokens is not None:body['max_tokens']=max_tokens
 for attempt in range(6):
  p=subprocess.run(SSH+['/opt/miniconda3/bin/python '+REMOTE],input=json.dumps(body),text=True,capture_output=True,timeout=1100)
  handshake_failure=p.returncode==255 and not p.stdout.strip() and ('kex_exchange_identification:' in p.stderr or 'ssh_exchange_identification:' in p.stderr)
  if not handshake_failure or attempt==5:break
  time.sleep(min(2**attempt,16))
 if p.returncode:raise RuntimeError('GPU model relay failed: '+p.stderr[-1500:])
 data=json.loads(p.stdout)
 if not data.get('choices'):raise RuntimeError('Empty model response')
 return data
def ns(x):
 if isinstance(x,dict):return types.SimpleNamespace(**{k:ns(v) for k,v in x.items()})
 if isinstance(x,list):return [ns(v) for v in x]
 return x
def complete(model,messages,tools,temperature=0):
 from agent_harness.agent_loop import _FakeResponse
 data=request(messages,tools,temperature)
 for choice in data['choices']:choice['message'].setdefault('tool_calls',None)
 return _FakeResponse(ns(data))
