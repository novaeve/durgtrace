"""A case-local Responses adapter, preserving native Codex tools and isolating provider evidence."""
from pathlib import Path
import json,os,socket,subprocess,time
import requests
from relay import Relay
from process_cleanup import stop_group
PROXY=Path('/data2/chenfuxin/molclaw_20260924/isolated_env/bin/litellm')
class Bridge:
 def __init__(self,out):
  self.out=Path(out);self.proc=None;self.server=None;self.relay=Relay(out)
 def start(self):
  self.server=self.relay.service()
  with socket.socket() as sock:
   sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
  config={'model_list':[{'model_name':'*','litellm_params':{
    'model':'openai/deepseek-v4.1-flash','use_chat_completions_api':True,
    'api_base':f'http://127.0.0.1:{self.server.server_port}/v1',
    'api_key':'local-only','temperature':0,'extra_body':{'enable_thinking':False}}}],
    'litellm_settings':{'drop_params':True,'set_verbose':False},
    'general_settings':{'disable_spend_logs':True}}
  path=self.out/'proxy_config.json';path.write_text(json.dumps(config))
  with (self.out/'proxy.log').open('w') as log:
   self.proc=subprocess.Popen([str(PROXY),'--config',str(path),'--host','127.0.0.1',
     '--port',str(self.port)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
     env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',LITELLM_LOG='ERROR'))
  deadline=time.monotonic()+120
  while time.monotonic()<deadline:
   if self.proc.poll() is not None:raise RuntimeError('Case proxy exited during startup')
   try:
    if requests.get(f'http://127.0.0.1:{self.port}/health/liveliness',timeout=1).status_code==200:return self
   except requests.RequestException:pass
   time.sleep(.5)
  raise TimeoutError('Case proxy startup exceeded 120 seconds')
 def close(self):
  if self.proc:
   stop_group(self.proc.pid)
   if self.proc.poll() is None:self.proc.wait(timeout=20)
  if self.server:self.server.shutdown();self.server.server_close()
 def __enter__(self):
  try:return self.start()
  except Exception:self.close();raise
 def __exit__(self,*args):self.close()

