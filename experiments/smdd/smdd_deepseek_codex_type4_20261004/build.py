from pathlib import Path
r=Path(__file__).resolve().parent
s=(r/'original_runtime.py').read_text()
s=s.replace('DeepSeek high transport','DeepSeek non-thinking transport')
s=s.replace("'enable_thinking':True,'reasoning_effort':'high'","'enable_thinking':False")
s=s.replace("enable_thinking=True,reasoning_effort='high'","enable_thinking=False")
start=s.index('def gpu_run(');end=s.index('\nfrom agent_harness.tools',start)
s=s[:start]+'''def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
 from gpu_slots import acquire
 Path(out).mkdir(parents=True,exist_ok=True)
 with acquire(Path(log_path).parent) as (gpu,descriptors):
  args=[str(BOLTZ),'-m','boltz.main','predict',str(yaml_path),'--out_dir',str(out),'--cache','/data2/chenfuxin/boltz-cache','--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--seed',str(seed),'--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
  dump(Path(log_path).parent/'boltz_provenance.json',{'argv':args,'gpu':gpu})
  with open(log_path,'w') as f:p=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,pass_fds=descriptors)
  return p.returncode
''' +s[end:]
s=s.replace("ROOT=Path(__file__).resolve().parent","ROOT=Path(__file__).resolve().parent\nfor proxy in ('http_proxy','https_proxy','all_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'):os.environ.pop(proxy,None)")
(r/'runtime.py').write_text(s)
s=(r/'type3_run.py').read_text()
s=s.replace("BASE=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')","BASE=ROOT")
s=s.replace("CODEX=Path('/data2/chenfuxin/smdd_codex_type2_bailian_20260929/bin/codex')","CODEX=ROOT/'bin/codex'")
s=s.replace("'model_reasoning_effort':'high',",'')
s=s.replace("'enable_thinking':True,'reasoning_effort':'high'","'enable_thinking':False")
s=s.replace("'mcp_servers.smdd.tool_timeout_sec':2400","'mcp_servers.smdd.tool_timeout_sec':28800")
start=s.index('def configure_gpu():');end=s.index('\nclass Boundary:',start)
s=s[:start]+"def configure_gpu():\n    os.environ['PYTORCH_CUDA_ALLOC_CONF']='expandable_segments:True'\n"+s[end:]
start=s.index('def sandbox(');end=s.index('\ndef command(',start)
s=s[:start]+'''def sandbox(work,port):
    args=['bwrap','--die-with-parent','--new-session','--unshare-pid','--unshare-ipc','--unshare-uts']
    for p in ['/usr','/bin','/lib','/lib64','/etc','/opt/codex-node']:
        if Path(p).exists():args+=['--ro-bind',p,p]
    args+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--dir','/root','--ro-bind',str(CODEX),'/runner/codex','--bind',str(work),'/workspace','--chdir','/workspace','--clearenv']
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/workspace/.home','CODEX_HOME':'/workspace/.codex','BAILIAN_API_KEY':'local-only','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    for k,v in env.items():args+=['--setenv',k,v]
    return args
''' +s[end:]
start=s.index("    if method=='molclaw':",s.index('def command'));end=s.index("    values={'model_provider'",start)
s=s[:start]+s[end:]
s=s.replace("out=ROOT/('smoke' if smoke else 'runs')/method/tid","out=ROOT/('preflight' if smoke else 'runs')/method/tid")
start=s.index('    public=Path(obfuscate_task(');end=s.index("    if smoke:prompt=",start)
s=s[:start]+'''    public=BASE/'public_inputs'/tid
    assert {p.name for p in public.iterdir()}=={'complex.pdb','reference.sdf'}
    for p in public.iterdir():shutil.copyfile(p,work/p.name)
    task=json.loads((BASE/'tasks'/f'{tid}.json').read_text())
    prompt=f"## Task\\n\\n{task['description']}\\n\\nYour workspace at /workspace contains the task files. Start by examining them."
''' +s[end:]
s=s.replace('timeout=86400','timeout=43200')
start=s.index('\ndef main():')
s=s[:start]+'''\ndef main():
    a=argparse.ArgumentParser();a.add_argument('method',choices=['codex','deepseek']);a.add_argument('--task',required=True);a.add_argument('--smoke',action='store_true');args=a.parse_args()
    configure_gpu()
    if args.method=='deepseek':
        out=ROOT/('preflight' if args.smoke else 'runs')/'deepseek'/args.task;out.mkdir(parents=True,exist_ok=True)
        task=json.loads((ROOT/'tasks'/f'{args.task}.json').read_text())
        result=runtime.baseline(task,ROOT/'public_inputs'/args.task,out)
        dump(out/'result.json',result)
    else:result=job('codex',args.task,0,args.smoke)
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
'''
(r/'run.py').write_text(s)
for name in ['runtime.py','run.py','gpu_slots.py']:compile((r/name).read_text(),name,'exec')
print('new deployment syntax checked; official SMDD loop and tools remain unchanged')
