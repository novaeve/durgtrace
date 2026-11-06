"""Acquire a shared GPU lock and wait for near-full VRAM before prediction."""
from pathlib import Path
import os,time,fcntl,subprocess
from runtime import BOLTZ,dump
BASE=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')
def gpu_run(yaml_path,out,log_path,samples=10,seed=42,timeout=1800):
    lockroot=Path('/data2/chenfuxin/liddia_smdd_type4_20260928')
    while True:
        available={}
        for gpu in ['0','1','3','4','5','6','7']:
            with (lockroot/f'boltz_gpu{gpu}.lock').open('a') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:continue
                free=int(subprocess.check_output(['nvidia-smi','-i',gpu,'--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
                available[gpu]=free
                if free<31500:continue
                args=[str(BOLTZ),str(BASE/'boltz_lowmem_entry.py'),'predict',str(yaml_path),'--out_dir',str(out),'--cache','/data2/chenfuxin/boltz-cache','--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--seed',str(seed),'--diffusion_samples_affinity',str(samples),'--max_parallel_samples','1']
                env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu,PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2')
                dump(Path(log_path).parent/'boltz_provenance.json',{'argv':args,'gpu':gpu,'free_mib_at_launch':free})
                dump(Path(log_path).parent/'resource_wait.json',{'status':'running','gpu':gpu,'time':time.time()})
                with open(log_path,'w') as log:
                    proc=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
                return proc.returncode
        dump(Path(log_path).parent/'resource_wait.json',{'status':'waiting_for_idle_gpu','required_free_mib':31500,'observed_free_mib':available,'time':time.time()})
        time.sleep(30)
