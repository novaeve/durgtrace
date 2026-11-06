"""Host-only SMDD inference adapters. Never exposed to generated CODE actions."""
from pathlib import Path
import fcntl
import json
import os
import subprocess
import uuid
import yaml
from runtime_safety import ToolExecutionError, ResourceUnavailable, require_disk, require_gpu, select_gpu, wait_for_gpu

ROOT=Path('/data2/chenfuxin/liddia_smdd_type4_20260928')
INSTALL=Path('/data2/chenfuxin/agent_reproduction_20260928')

def isolated_python(script, job, timeout=300):
    job=Path(job).resolve();job.mkdir(parents=True,exist_ok=True)
    (job/'worker.py').write_text(script)
    cmd=['bwrap','--unshare-all','--die-with-parent','--new-session',
         '--ro-bind',str(ROOT/'evaluator_rootfs'),'/', '--proc','/proc','--dev','/dev',
         '--tmpfs','/tmp','--tmpfs','/root','--bind',str(job),'/work','--chdir','/work',
         '--clearenv','--setenv','PATH','/opt/conda/bin:/usr/bin:/bin',
         '--setenv','LD_LIBRARY_PATH','/opt/conda/lib','--setenv','HOME','/tmp',
         '--setenv','OMP_NUM_THREADS','1','--setenv','MKL_NUM_THREADS','1',
         '--setenv','OPENBLAS_NUM_THREADS','1','--setenv','CUDA_VISIBLE_DEVICES','',
         '/opt/conda/bin/python','/work/worker.py']
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError('Isolated worker timed out: '+str(job)) from exc
    (job/'stdout.log').write_text(result.stdout)
    (job/'stderr.log').write_text(result.stderr)
    if result.returncode:
        require_disk(job)
        raise ToolExecutionError('Isolated worker failed; see '+str(job/'stderr.log'))
    try:
        return json.loads((job/'result.json').read_text())
    except (FileNotFoundError,ValueError) as exc:
        raise ToolExecutionError('Isolated worker produced no valid result: '+str(job)) from exc

def admet(smiles, output):
    job=Path(output)/('admet_'+uuid.uuid4().hex[:12]);job.mkdir(parents=True)
    (job/'input.json').write_text(json.dumps({'smiles':smiles}))
    return isolated_python('''import json,functools,torch
from pathlib import Path
torch.load=functools.partial(torch.load,weights_only=False)
torch.set_num_threads(1)
from admet_ai import ADMETModel
model=ADMETModel()
pred=model.predict(smiles=json.loads(Path('input.json').read_text())['smiles'])
mapping={'hERG':'herg','BBB_Martins':'bbb','Solubility_AqSolDB':'solubility','CYP3A4_Veith':'cyp3a4','Clearance_Hepatocyte_AZ':'clearance','Caco2_Wang':'caco2','PPBR_AZ':'ppb','AMES':'ames'}
result={}
for col,name in mapping.items():
 for actual in pred:
  if col.lower() in actual.lower():
   val=pred[actual];result[name]=float(val.iloc[0] if hasattr(val,'iloc') else val);break
assert len(result)==8
Path('result.json').write_text(json.dumps(result))
''',job)

def boltz_payload(payload, output, gpu=1, samples=10, seed=42, job_name='input'):
    if Path(job_name).name!=job_name or not job_name or job_name in ('.','..'):raise ValueError('Invalid job name')
    require_disk(ROOT)
    gpu=wait_for_gpu(gpu,Path(output).parent/'resource_wait.json')
    job=Path(output)/('boltz_'+uuid.uuid4().hex[:12]);job.mkdir(parents=True)
    (job/(job_name+'.yaml')).write_text(yaml.safe_dump(payload))
    cmd=[str(INSTALL/'envs/boltz_smdd/bin/python'),'-m','boltz.main','predict',str(job/(job_name+'.yaml')),
         '--out_dir',str(job/'out'),'--cache','/data2/chenfuxin/boltz-cache',
         '--use_msa_server','--use_potentials','--accelerator','gpu','--devices','1',
         '--diffusion_samples',str(samples),'--diffusion_samples_affinity',str(samples),
         '--seed',str(seed),'--max_parallel_samples','1']
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),OMP_NUM_THREADS='2',
             OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2')
    (job/'provenance.json').write_text(json.dumps({'command':cmd,'gpu':gpu,'samples':samples,'seed':seed},indent=2))
    with (ROOT/f'boltz_gpu{gpu}.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        # Recheck after acquiring our GPU lock. Waiting must not spend another
        # oracle call or restart the planner.
        while True:
            try:
                require_gpu(gpu)
                break
            except ResourceUnavailable:
                import time
                time.sleep(60)
        with (job/'boltz.log').open('w') as log:
            try:
                subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                require_disk(job)
                raise ToolExecutionError('Boltz failed; see '+str(job/'boltz.log')) from exc
    try:
        result=json.loads((job/'out'/('boltz_results_'+job_name)/'predictions'/job_name/('affinity_'+job_name+'.json')).read_text())
        result['prediction_directory']=str(job/'out')
        return result
    except (FileNotFoundError,ValueError) as exc:
        raise ToolExecutionError('Boltz produced no valid affinity result; see '+str(job/'boltz.log')) from exc

def boltz(smiles, derived, output, gpu=1):
    payload={'version':1,'sequences':[{'protein':p} for p in derived['protein_sequences']]+[{'ligand':{'id':'LIG','smiles':smiles}}],
             'constraints':[{'pocket':{'binder':'LIG','contacts':derived['pocket_residues'],'max_distance':6.0,'force':True}}],
             'properties':[{'affinity':{'binder':'LIG'}}]}
    return boltz_payload(payload,output,gpu)
