import os,pathlib,json
ROOT=pathlib.Path(__file__).resolve().parent
values={}
for line in pathlib.Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text(encoding='utf-8-sig').splitlines():
 if '=' in line:
  k,v=line.split('=',1);values[k.strip().lower()]=v.strip().strip('"').strip("'")
os.environ['BAILIAN_API_KEY']=values['api_key']
cfg={'model_list':[{'model_name':'*','litellm_params':{'model':'openai/deepseek-v4.1-flash','api_base':values['base_url'],'api_key':'os.environ/BAILIAN_API_KEY','extra_body':{'enable_thinking':False}}}], 'litellm_settings':{'drop_params':True,'set_verbose':False},'general_settings':{'disable_spend_logs':True}}
(ROOT/'proxy_config.yaml').write_text(json.dumps(cfg))
os.execv(str(ROOT/'isolated_env/bin/litellm'),['litellm','--config',str(ROOT/'proxy_config.yaml'),'--host','127.0.0.1','--port','18745'])
