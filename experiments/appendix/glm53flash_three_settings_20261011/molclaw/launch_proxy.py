import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CLAW=Path('/data2/chenfuxin/molclaw_20260924')
port=json.loads((ROOT/'proxy_port.json').read_text())['port']
os.environ['MOLCLAW_GPT_API_KEY']='local-glm-boundary'
cfg={'model_list':[{'model_name':'*','litellm_params':{'model':'openai/glm-5.3-flash','api_base':'http://127.0.0.1:18855/v4','api_key':'os.environ/MOLCLAW_GPT_API_KEY','extra_body':{'reasoning_effort':'low'}}}], 'litellm_settings':{'use_chat_completions_url_for_anthropic_messages':True,'drop_params':True,'set_verbose':False,'callbacks':['audit_callback.audit_logger']},'general_settings':{'disable_spend_logs':True}}
config=ROOT/'proxy_config.yaml';config.write_text(json.dumps(cfg));os.chmod(config,0o600)
os.environ['PYTHONPATH']=str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')
os.chdir(ROOT)
os.execv(str(CLAW/'isolated_env/bin/litellm'),['litellm','--config',str(config),'--host','127.0.0.1','--port',str(port)])
