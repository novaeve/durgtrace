"""DeepSeek non-thinking transport and isolated deployment of official SMDD tools."""
from pathlib import Path
import sys,os,json,time,types,shlex,subprocess,shutil,fcntl
ROOT=Path(__file__).resolve().parent
for proxy in ('http_proxy','https_proxy','all_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'):os.environ.pop(proxy,None)
UPSTREAM=ROOT/'upstream'
ROOTFS=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/evaluator_rootfs')
BOLTZ=Path('/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python')
sys.path.insert(0,str(UPSTREAM))
import requests,yaml

def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));t.replace(p)

class API:
 def __init__(self,out):
  self.out=Path(out);self.calls=0;self.total_tokens=0;self.reasoning={}
  cfg={}
  for line in Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text(encoding='utf-8-sig').splitlines():
   if '=' in line and not line.lstrip().startswith('#'):
    k,v=line.split('=',1);cfg[k.strip().lower()]=v.strip().strip('\"').strip("'")
  self.url=cfg['base_url'].rstrip('/')+'/chat/completions';self.key=cfg['api_key']
 def complete(self,messages,tools=None,cap=None,temperature=1):
  self.calls+=1
  def clean(x):
   if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k!='cache_control'}
   if isinstance(x,list):return [clean(v) for v in x]
   return x
  messages=clean(messages)
  for m in messages:
   if m.get('role')=='assistant' and m.get('tool_calls'):
    m['reasoning_content']=self.reasoning.get(m['tool_calls'][0]['id'],'')
  body={'model':'deepseek-v4.1-flash','messages':messages,'enable_thinking':False,'temperature':temperature}
  if tools:body['tools']=clean(tools)
  if cap:body['max_tokens']=cap
  rec={'request':body,'started':time.time(),'attempts':[]};path=self.out/'api'/f'{self.calls:03d}.json'
  for attempt in range(26):
   try:
    r=requests.post(self.url,json=body,headers={'Authorization':'Bearer '+self.key},timeout=(25,600))
    rec['attempts'].append({'status':r.status_code,'time':time.time()})
    if r.status_code in [408,429,500,502,503,504]:
     dump(path,rec);time.sleep(min(2**min(attempt,6),60));continue
    if r.status_code!=200:
     rec['error']=r.text[:1000];dump(path,rec);raise RuntimeError('API_HTTP_'+str(r.status_code))
    data=r.json();rec.update(response=data,ended=time.time());dump(path,rec)
    if data.get('model')!='deepseek-v4.1-flash':raise RuntimeError('Unexpected model returned')
    self.total_tokens+=data.get('usage',{}).get('total_tokens',0)
    msg=data['choices'][0]['message']
    for tc in msg.get('tool_calls') or []:self.reasoning[tc['id']]=msg.get('reasoning_content','')
    return data
   except requests.RequestException as e:
    rec['attempts'].append({'error':type(e).__name__});dump(path,rec);time.sleep(min(2**min(attempt,6),60))
  raise RuntimeError('API retries exhausted')

def isolated(cmd,work,timeout=300,binds=None):
 work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
 if cmd[0] in ['python','/opt/oracle/bin/python']:cmd=['/opt/conda/bin/python']+cmd[1:]
 args=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind',str(ROOTFS),'/',
 '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/root','--tmpfs','/eval','--tmpfs','/queue','--tmpfs','/work',
 '--bind',str(work),'/workspace','--chdir','/workspace','--clearenv',
 '--setenv','PATH','/opt/conda/bin:/usr/bin:/bin','--setenv','LD_LIBRARY_PATH','/opt/conda/lib',
 '--setenv','HOME','/tmp','--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1','--setenv','MKL_NUM_THREADS','1','--setenv','CUDA_VISIBLE_DEVICES','']
 if binds:args+=binds
 p=subprocess.run(args+cmd,capture_output=True,text=True,timeout=timeout)
 return p.stdout+p.stderr,p.returncode

def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
 from gpu_slots import acquire
 Path(out).mkdir(parents=True,exist_ok=True)
 with acquire(Path(log_path).parent) as (gpu,descriptors):
  args=[str(BOLTZ),'-m','boltz.main','predict',str(yaml_path),'--out_dir',str(out),'--cache','/data2/chenfuxin/boltz-cache','--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--seed',str(seed),'--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
  dump(Path(log_path).parent/'boltz_provenance.json',{'argv':args,'gpu':gpu})
  with open(log_path,'w') as f:p=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,pass_fds=descriptors)
  return p.returncode

from agent_harness.tools import ToolExecutor
class Executor(ToolExecutor):
 def __init__(self,container_id,config,workspace_dir='/workspace'):
  super().__init__(container_id,config,workspace_dir);self.work=Path(container_id).resolve()
 def path(self,p):
  s=str(p)
  if s.startswith('/workspace/'):s=s[len('/workspace/'):]
  q=(self.work/s).resolve()
  if not q.is_relative_to(self.work):raise ValueError('Path outside isolated workspace')
  return q
 def _copy_to_container(self,src,dst):
  dst=self.path(dst);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 def _copy_from_container(self,src,dst):shutil.copyfile(self.path(src),dst)
 def _docker_exec(self,cmd,timeout=120):return isolated(cmd,self.work,timeout)
 def _docker_exec_shell(self,cmd,timeout=120):
  if not cmd.startswith('/opt/oracle/bin/boltz predict '):return isolated(['bash','-c',cmd],self.work,timeout)
  args=shlex.split(cmd);yp=self.path(args[2]);out=self.path(args[args.index('--out_dir')+1]);out.mkdir(parents=True,exist_ok=True)
  # These paths are copied out of the sandbox, not interpreted as host shell code.
  payload=yaml.safe_load(yp.read_text())
  for row in payload.get('sequences',[]):
   for entity in row.values():
    if 'msa' in entity or 'ccd' in entity:raise ValueError('Unexpected file-dependent input')
  samples=int(args[args.index('--diffusion_samples')+1]);seed=int(args[args.index('--seed')+1])
  log=out/'boltz.log';rc=gpu_run(yp,out,log,samples,seed,timeout)
  return log.read_text(errors='replace'),rc

def baseline(task,public,out):
 sys.modules.setdefault('litellm',types.ModuleType('litellm'))
 from agent_harness import agent_loop
 from agent_harness.config import AgentConfig
 from dataclasses import asdict
 api=API(out)
 def llm(model,messages,tools,temperature=1):
  d=api.complete(messages,tools=tools,temperature=temperature);d['choices'][0]['message'].setdefault('tool_calls',None)
  return agent_loop._FakeResponse(json.loads(json.dumps(d),object_hook=lambda x:types.SimpleNamespace(**x)))
 agent_loop.call_llm_completions=llm;agent_loop.ToolExecutor=Executor
 config=AgentConfig(model='openai/deepseek-v4.1-flash')
 dump(out/'config.json',dict(asdict(config),enable_thinking=False,execution='bubblewrap evaluator-rootfs; host Boltz transport'))
 work=out/'workspace';work.mkdir(exist_ok=True)
 for p in public.iterdir():shutil.copyfile(p,work/p.name)
 result=agent_loop.run_agent(task,str(public),config,str(work),str(out))
 pred=work/'solution.smi'
 if pred.exists():shutil.copyfile(pred,out/'solution.smi')
 return asdict(result)
