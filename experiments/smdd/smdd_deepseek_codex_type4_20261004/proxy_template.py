"""Host-only credentials; dedicated Responses->Chat provider adapter."""
import json,os,threading,time,subprocess
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import requests
from pathlib import Path
ROOT=Path(__file__).resolve().parent
values={}
for line in Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,v=line.strip().removeprefix('export ').split('=',1);values[k.strip().lower()]=v.strip().strip('"').strip("'")
class Boundary(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        body.update(model='deepseek-v4.1-flash',temperature=0,enable_thinking=False)
        for key in ('reasoning_effort','reasoning','thinking'):body.pop(key,None)
        with (ROOT/'request_settings.jsonl').open('a') as f:
            f.write(json.dumps({'time':time.time(),**{k:body.get(k) for k in ('model','temperature','enable_thinking','reasoning_effort','thinking','max_tokens','stream')}})+'\n')
        try:
            with requests.post(values['base_url'].rstrip('/')+'/chat/completions',json=body,headers={'Authorization':'Bearer '+values['api_key']},stream=True,timeout=(30,300)) as response:
                self.send_response(response.status_code)
                self.send_header('Content-Type',response.headers.get('Content-Type','application/json'))
                self.send_header('Connection','close');self.end_headers()
                for chunk in response.iter_content(chunk_size=1):
                    if chunk:self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):pass
        finally:self.close_connection=True
boundary=ThreadingHTTPServer(('127.0.0.1',0),Boundary)
threading.Thread(target=boundary.serve_forever,daemon=True).start()
cfg={'model_list':[{'model_name':'*','litellm_params':{'model':'openai/deepseek-v4.1-flash','use_chat_completions_api':True,'api_base':'http://127.0.0.1:'+str(boundary.server_port)+'/v1','api_key':'local-only','temperature':0,'extra_body':{'enable_thinking':False}}}],'litellm_settings':{'drop_params':True,'set_verbose':False},'general_settings':{'disable_spend_logs':True}}
(ROOT/'proxy_config.json').write_text(json.dumps(cfg))
raise SystemExit(subprocess.call(['/data2/chenfuxin/molclaw_20260924/isolated_env/bin/litellm','--config',str(ROOT/'proxy_config.json'),'--host','127.0.0.1','--port','18750']))
