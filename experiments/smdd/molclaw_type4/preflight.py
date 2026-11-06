"""Environment validation only; does not call the model API or solve a task."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
def run(args,timeout=120,env=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env=env)
 print(p.stdout,flush=True)
 if p.returncode:print(p.stderr,flush=True);raise RuntimeError('Preflight subprocess failed')
 return p.stdout
ids=sorted(p.name for p in (ROOT/'tasks').glob('smdd_004_*') if (p/'task.yaml').exists())
assert len(ids)==340, len(ids)
(ROOT/'task_list.txt').write_text('\n'.join(ids)+'\n')
report={'started':time.time(),'tasks':len(ids),'model_api_called':False}
report['gpu']=run(['nvidia-smi','--query-gpu=index,name,memory.total,memory.free','--format=csv,noheader'])
report['node']=run([str(ROOT/'node/bin/node'),'--version'])
env=dict(os.environ,PATH=str(ROOT/'node/bin')+':'+os.environ['PATH'],PYTHONNOUSERSITE='1',LD_LIBRARY_PATH=str(ROOT/'rootfs/opt/conda/lib'))
report['claude']=run([str(ROOT/'cli_runtime/node_modules/.bin/claude'),'--version'],env=env)
run([str(ROOT/'proxy_env/bin/python'),'-c','import requests,yaml,litellm;print("proxy dependencies OK")'],env=env)
py=ROOT/'rootfs/opt/conda/bin/python'
report['gpu_python']=run([str(py),'-c','import torch,boltz,rdkit;print(torch.__version__,boltz.__file__);assert torch.cuda.device_count()==2;[(print(torch.cuda.get_device_name(i)),torch.ones((128,128),device=f"cuda:{i}").sum().item()) for i in range(2)]'],env=env)
sys.path.insert(0,str(ROOT))
from runtime import isolated
output,rc=isolated(['python','-c','import rdkit,torch;from rdkit import Chem;assert Chem.MolFromSmiles("CCO");print("isolated scientific Python OK")'],ROOT/'preflight/work')
print(output,flush=True);assert rc==0
from run import sandbox
run(sandbox(ROOT/'preflight/work',1)+[str(ROOT/'cli_runtime/node_modules/.bin/claude'),'--version'])
report['ended']=time.time()
(ROOT/'preflight_environment.json').write_text(json.dumps(report,indent=2))
print('ENVIRONMENT_PREFLIGHT_OK; Boltz and model smoke still required',flush=True)
