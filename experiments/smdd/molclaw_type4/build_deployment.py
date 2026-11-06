from pathlib import Path
ROOT=Path(__file__).resolve().parent
s=(ROOT/'source_runtime.py').read_text()
s=s.replace('DeepSeek high transport','DeepSeek non-thinking transport')
s=s.replace("ROOT=Path(__file__).resolve().parent", "ROOT=Path(__file__).resolve().parent\n# This host's inherited localhost proxy is unavailable; scope direct access to this experiment.\nfor _proxy in ('http_proxy','https_proxy','all_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'):\n os.environ.pop(_proxy,None)")
s=s.replace("ROOTFS=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/evaluator_rootfs')","ROOTFS=ROOT/'rootfs'")
s=s.replace("BOLTZ=Path('/data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python')","BOLTZ=ROOTFS/'opt/conda/bin/python'")
s=s.replace("Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env')","(ROOT/'private/model.env')")
s=s.replace("'enable_thinking':True,'reasoning_effort':'high'", "'enable_thinking':False")
s=s.replace("enable_thinking=True,reasoning_effort='high'", "enable_thinking=False")
start=s.index('def gpu_run(');end=s.index('\nfrom agent_harness.tools',start)
s=s[:start]+'''def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
 from gpu_slots import acquire
 Path(out).mkdir(parents=True,exist_ok=True)
 with acquire(Path(log_path).parent) as gpu:
  args=[str(BOLTZ),'-m','boltz.main','predict',str(yaml_path),'--out_dir',str(out),'--cache',str(ROOT/'boltz_cache'),'--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--seed',str(seed),'--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),PYTHONNOUSERSITE='1',LD_LIBRARY_PATH=str(ROOTFS/'opt/conda/lib'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
  dump(Path(log_path).parent/'boltz_provenance.json',{'argv':args,'gpu':gpu})
  with open(log_path,'w') as f:p=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
  return p.returncode
''' +s[end:]
(ROOT/'runtime.py').write_text(s)
s=(ROOT/'source_run.py').read_text()
s=s.replace("BASE=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')","BASE=ROOT")
s=s.replace("MOL=Path('/data2/chenfuxin/molclaw_20260924')","MOL=ROOT")
s='\n'.join(line for line in s.splitlines() if not line.startswith('CODEX=') and 'source=inspect.getsource(runtime.gpu_run)' not in line and "ns=dict(runtime.__dict__)" not in line and "runtime.gpu_run=ns['gpu_run']" not in line)+'\n'
s=s.replace("MOL/'runtime", "MOL/'cli_runtime")
s=s.replace("'--ro-bind','/opt/codex-node','/opt/codex-node','--ro-bind',str(CODEX),'/runner/codex',", "'--ro-bind',str(ROOT/'node'),'/opt/codex-node',")
s=s.replace("MOL/'source/MolClaw-main/", "MOL/'molclaw_source/")
s=s.replace("[str(MOL/'isolated_env/bin/litellm'),", "[str(MOL/'proxy_env/bin/python'),str(MOL/'proxy_env/bin/litellm'),")
s=s.replace("'CLAUDE_CODE_EFFORT_LEVEL':'high',", "'MAX_THINKING_TOKENS':'0',")
s=s.replace("'--effort','high',", "")
s=s.replace("'enable_thinking':True,'reasoning_effort':'high'", "'enable_thinking':False")
s=s.replace("env['MCP_TOOL_TIMEOUT']='2400000'", "env['MCP_TOOL_TIMEOUT']='14400000'")
start=s.index("    values={'model_provider'");end=s.index('\n\ndef job(',start)
s=s[:start]+"    raise ValueError('Only MolClaw is supported by this deployment')\n"+s[end:]
start=s.index('\ndef main():')
s=s[:start]+'''
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--task',required=True);ap.add_argument('--index',type=int,default=0);ap.add_argument('--smoke',action='store_true');a=ap.parse_args()
    configure_gpu()
    if not a.task.startswith('smdd_004_') or '/' in a.task:raise ValueError('Type4 task required')
    result=job('molclaw',a.task,a.index,a.smoke)
    if result['status']=='error':raise SystemExit(1)
    if not a.smoke:
        from evaluate import evaluate
        scored=evaluate(a.task,'molclaw')
        if scored['status']=='errored':raise SystemExit(2)
if __name__=='__main__':main()
'''
(ROOT/'run.py').write_text(s)
(ROOT/'evaluate.py').write_text((ROOT/'source_evaluate.py').read_text())
for name in ['runtime.py','run.py','evaluate.py','gpu_slots.py','scheduler.py']:
 compile((ROOT/name).read_text(),name,'exec')
print('Deployment syntax verified')
