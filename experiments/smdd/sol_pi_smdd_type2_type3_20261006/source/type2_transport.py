"""Host transport only. Model-generated code executes in the isolated old image."""
from pathlib import Path
import sys,os,json,time,shlex,uuid,subprocess,tarfile,types
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import paramiko,requests

def dump(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));tmp.replace(p)

class CPU:
    def __init__(self):
        self.c=paramiko.SSHClient();self.c.load_host_keys(str(ROOT/'private/known_hosts'))
        self.c.set_missing_host_key_policy(paramiko.RejectPolicy())
        self.c.connect('159.138.92.174',username='chenfuxin',password=(ROOT/'private/cpu_password').read_text(),look_for_keys=False,allow_agent=False,timeout=25)
        self.c.get_transport().set_keepalive(15)
        self.s=self.c.open_sftp()
    def run(self,args,timeout=300):
        command=shlex.join(args)
        channel=self.c.get_transport().open_session();channel.set_combine_stderr(True)
        channel.exec_command(command);start=time.monotonic();output=[]
        while True:
            if channel.recv_ready():output.append(channel.recv(65536))
            elif channel.exit_status_ready():break
            elif time.monotonic()-start>timeout:
                channel.close();raise subprocess.TimeoutExpired(args,timeout)
            else:time.sleep(.05)
        return b''.join(output).decode(errors='replace'),channel.recv_exit_status()
    def checked(self,args,timeout=300):
        text,rc=self.run(args,timeout)
        if rc:raise RuntimeError(f'CPU command failed ({rc}): '+text[-2000:])
        return text
    def upload(self,path):
        dest='/tmp/smdd-transfer-'+uuid.uuid4().hex
        self.s.put(str(path),dest);return dest
    def close(self):self.s.close();self.c.close()

class API:
    def __init__(self,out):
        self.out=Path(out);self.calls=0;self.total_tokens=0
        cfg={}
        for line in Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);cfg[k.strip().lower()]=v.strip().strip('"').strip("'")
        self.url=cfg['base_url'].rstrip('/')+'/chat/completions';self.key=cfg['api_key']
    def complete(self,messages,tools=None,cap=None,temperature=1.0):
        self.calls+=1
        def clean(x):
            if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k!='cache_control'}
            if isinstance(x,list):return [clean(v) for v in x]
            return x
        body={'model':'deepseek-v4.1-flash','messages':clean(messages),'temperature':temperature,'enable_thinking':False}
        if tools:body['tools']=clean(tools)
        if cap is not None:body['max_tokens']=cap
        record={'request':body,'started':time.time(),'attempts':[]}
        path=self.out/'api'/f'{self.calls:03d}.json'
        for attempt in range(26):
            try:
                res=requests.post(self.url,json=body,headers={'Authorization':'Bearer '+self.key},timeout=(25,180))
                record['attempts'].append({'status':res.status_code,'time':time.time()})
                if res.status_code in [408,429,500,502,503,504]:
                    dump(path,record);time.sleep(min(2**min(attempt,6),60));continue
                if res.status_code!=200:
                    record['error_body']=res.text[:2000];dump(path,record)
                    raise RuntimeError('API_HTTP_'+str(res.status_code))
                data=res.json();record.update(response=data,ended=time.time());dump(path,record)
                self.total_tokens+=data.get('usage',{}).get('total_tokens',0)
                return data
            except requests.RequestException as e:
                record['attempts'].append({'error':type(e).__name__});dump(path,record)
                time.sleep(min(2**min(attempt,6),60))
        raise RuntimeError('API transport retries exhausted')

def install_executor(cpu):
    from agent_harness.tools import ToolExecutor
    class Executor(ToolExecutor):
        def _docker_exec(self,cmd,timeout=120):
            return cpu.run(['docker','exec','--workdir',self.workspace_dir,self.container_id]+cmd,timeout)
        def _copy_to_container(self,local_path,container_path):
            remote=cpu.upload(local_path)
            try:cpu.checked(['docker','cp',remote,f'{self.container_id}:{container_path}'])
            finally:cpu.s.remove(remote)
        def _copy_from_container(self,container_path,local_path):
            remote='/tmp/smdd-transfer-'+uuid.uuid4().hex
            try:
                cpu.checked(['docker','cp',f'{self.container_id}:{container_path}',remote])
                cpu.s.get(remote,str(local_path))
            finally:
                try:cpu.s.remove(remote)
                except OSError:pass
        def _docker_exec_shell(self,cmd,timeout=120):
            if not cmd.startswith('/opt/oracle/bin/boltz predict '):
                return self._docker_exec(['bash','-c',cmd],timeout)
            argv=shlex.split(cmd);job=ROOT/'gpu_jobs'/uuid.uuid4().hex;job.mkdir(parents=True)
            source=argv[2];out_index=argv.index('--out_dir')+1;container_out=argv[out_index]
            local_yaml=job/Path(source).name;self._copy_from_container(source,local_yaml)
            local_out=job/'out'
            argv[2]=str(local_yaml);argv[out_index]=str(local_out)
            argv=['/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python','-m','boltz.main']+argv[1:]
            argv+=['--cache','/data2/chenfuxin/boltz-cache']
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=os.environ.get('SMDD_TYPE2_GPU','4'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
            dump(job/'provenance.json',{'original_command':cmd,'actual_argv':argv,'gpu':env['CUDA_VISIBLE_DEVICES']})
            with (job/'boltz.log').open('w') as log:
                proc=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=timeout)
            if local_out.exists():
                archive=job/'result.tar.gz'
                with tarfile.open(archive,'w:gz') as t:
                    for p in local_out.iterdir():t.add(p,arcname=p.name)
                remote=cpu.upload(archive)
                try:
                    cpu.checked(['docker','exec',self.container_id,'mkdir','-p',container_out])
                    cpu.checked(['docker','cp',remote,self.container_id+':/tmp/boltz-result.tar.gz'])
                    cpu.checked(['docker','exec',self.container_id,'tar','-xzf','/tmp/boltz-result.tar.gz','-C',container_out])
                finally:cpu.s.remove(remote)
            return (job/'boltz.log').read_text(errors='replace'),proc.returncode
    return Executor

def baseline(task,public_dir,out):
    # Replace only API transport and Docker location; native loop remains frozen.
    sys.modules.setdefault('litellm',types.ModuleType('litellm'))
    from agent_harness import agent_loop
    from agent_harness.config import AgentConfig
    from dataclasses import asdict
    cpu=CPU();name='smdd-t2-ds-'+uuid.uuid4().hex[:12]
    api=API(out)
    def llm(model,messages,tools,temperature=1.0):
        data=api.complete(messages,tools=tools,temperature=temperature)
        data['choices'][0]['message'].setdefault('tool_calls',None)
        obj=json.loads(json.dumps(data),object_hook=lambda d:types.SimpleNamespace(**d))
        return agent_loop._FakeResponse(obj)
    agent_loop.call_llm_completions=llm
    agent_loop.ToolExecutor=install_executor(cpu)
    config=AgentConfig(model='openai/deepseek-v4.1-flash')
    dump(Path(out)/'config.json',asdict(config))
    try:
        cpu.checked(['docker','create','--name',name,'--network','smdd-internal','--shm-size=32g','-w','/workspace','smdd-agent:latest','sleep','infinity'])
        cpu.checked(['docker','start',name])
        ex=agent_loop.ToolExecutor(name,config)
        ex._copy_to_container(Path(public_dir)/'receptor.pdb','/workspace/receptor.pdb')
        result=agent_loop.run_agent(task,str(public_dir),config,name,str(out))
        try:ex._copy_from_container('/workspace/solution.csv',Path(out)/'solution.csv')
        except RuntimeError:pass
        return asdict(result)
    finally:
        cpu.run(['docker','rm','-f',name]);cpu.close()
