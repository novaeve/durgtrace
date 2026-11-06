import json,subprocess,os
from pathlib import Path
BASE=Path(__file__).resolve().parent
def provider_env():
 cfg={}
 for line in Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text().splitlines():
  line=line.strip().removeprefix('export ')
  if '=' in line and not line.startswith('#'):
   k,v=line.split('=',1);cfg[k.strip().lower()]=v.strip().strip('\"\'')
 env=os.environ.copy();env['BAILIAN_API_KEY']=cfg['api_key'];env['PATH']=str(BASE/'bin')+':'+env['PATH'];return cfg,env
def config_args(base_url):
 values={'model_provider':'bailian','web_search':'disabled','model_providers.bailian.name':'Alibaba Bailian','model_providers.bailian.base_url':base_url,'model_providers.bailian.env_key':'BAILIAN_API_KEY','model_providers.bailian.wire_api':'responses','model_providers.bailian.requires_openai_auth':False,'model_providers.bailian.request_max_retries':2,'model_providers.bailian.stream_max_retries':2,'model_providers.bailian.stream_idle_timeout_ms':300000}
 args=[]
 for k,v in values.items():args+=['-c',k+'='+json.dumps(v)]
 return args
def command(base_url,out,prompt):
 return [str(BASE/'bin/codex'),'exec','--ephemeral','--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','--json','-m','deepseek-v4.1-flash',*config_args(base_url),'-o',str(out/'last_message.txt'),prompt]
if __name__=='__main__':
 work=BASE/'smoke';work.mkdir(exist_ok=True);cfg,env=provider_env()
 prompt='Work only in the current directory. Use the shell tool to run Python, import rdkit and Bio, compute 17*19, and write the number to probe.txt. Read it back with a tool. Finish by saying SMOKE_OK. Do not inspect environment variables, credentials, or other directories.'
 with (work/'events.jsonl').open('w') as o,(work/'stderr.log').open('w') as e:
  try:r=subprocess.run(command(cfg['base_url'],work,prompt),cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=o,stderr=e,timeout=180);rc=r.returncode
  except subprocess.TimeoutExpired:rc=124
 text=(work/'probe.txt').read_text().strip() if (work/'probe.txt').exists() else None
 result={'exit_code':rc,'probe_value':text,'passed':rc==0 and text=='323','model':'deepseek-v4.1-flash','provider':'Alibaba Bailian'}
 (work/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 if not result['passed']:
  for f in ['stderr.log','events.jsonl']:print((work/f).read_text()[-5000:].replace(cfg['api_key'],'[REDACTED]'))
 raise SystemExit(0 if result['passed'] else 1)
