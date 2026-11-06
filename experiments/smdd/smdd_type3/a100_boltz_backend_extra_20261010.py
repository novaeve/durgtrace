"""A100-only Boltz compute, shared two-GPU admission for tools and official evaluator."""

# Migration: record the machine that actually executes each future prediction.
import os as _migration_os
import socket as _migration_socket
import subprocess as _migration_subprocess
_EXECUTION_HOST = _migration_os.environ.get('SMDD_EXECUTION_HOST', _migration_socket.gethostname())
try:
    _migration_gpu_names = _migration_subprocess.check_output(
        ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
        text=True, stderr=_migration_subprocess.DEVNULL, timeout=10).strip().splitlines()
except (OSError, _migration_subprocess.SubprocessError):
    _migration_gpu_names = []
_GPU_COUNT = len(_migration_gpu_names)
_GPU_MODEL = _migration_gpu_names[0] if _migration_gpu_names else 'unavailable'

import base64,io,json,os,queue,subprocess,time,uuid,zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import yaml
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'boltz-cache'
TMP=ROOT/'compute-tmp';TMP.mkdir(exist_ok=True)
TORCH_CACHE=ROOT/'torch-cache';TORCH_CACHE.mkdir(exist_ok=True)
PY=ROOT/'boltz-env/bin/python'
SLOTS=queue.Queue()
for device in [0,1]:SLOTS.put(device)

def predict(payload):
    job=ROOT/'jobs_extra_20261010'/uuid.uuid4().hex;job.mkdir(parents=True)
    if 'yaml_text' in payload:
        doc=yaml.safe_load(payload['yaml_text']);name=Path(payload.get('yaml_name','input.yaml')).name
    else:
        rows=[{'protein':{'id':p['id'],'sequence':p['sequence']}} for p in payload['protein_sequences']]
        rows.append({'ligand':{'id':'LIG','smiles':payload['smiles']}})
        rows.extend({'ligand':p} for p in payload.get('co_ligand_smiles',[]) or [])
        doc={'version':1,'sequences':rows,'properties':[{'affinity':{'binder':'LIG'}}]};name='input.yaml'
        if payload.get('pocket_residues'):doc['constraints']=[{'pocket':{'binder':'LIG','contacts':payload['pocket_residues'],'max_distance':6.0,'force':True}}]
    for row in doc['sequences']:
        for value in row.values():
            if 'msa' in value or 'ccd' in value:raise ValueError('Client filesystem references are unsupported')
    samples=int(payload.get('num_samples',10));assert 1<=samples<=10
    yp=job/name;yp.write_text(yaml.safe_dump(doc,sort_keys=False));out=job/'out'
    waiting=time.time();device=SLOTS.get(timeout=21600)
    try:
        argv=[str(PY),'-m','boltz.main','predict',str(yp),'--out_dir',str(out),'--cache',str(CACHE),
              '--use_msa_server','--use_potentials','--diffusion_samples',str(samples),'--diffusion_samples_affinity',str(samples),
              '--seed',str(int(payload.get('seed',42))),'--max_parallel_samples','2']
        clean={k:v for k,v in os.environ.items() if k.upper() not in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']}
        env=dict(clean,CUDA_VISIBLE_DEVICES=str(device),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',
                 PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',TMPDIR=str(TMP),
                 TORCHINDUCTOR_CACHE_DIR=str(TORCH_CACHE/'inductor'),TRITON_CACHE_DIR=str(TORCH_CACHE/'triton'))
        provenance={'argv':argv,'gpu':device,'gpu_model':_GPU_MODEL,'host':_EXECUTION_HOST,'request':payload,
                    'started':time.time(),'queue_seconds':time.time()-waiting,'boltz_version':'2.2.1','source_protocol':'official MSA, potentials, 10 diffusion and affinity samples, seed42'}
        (job/'provenance.json').write_text(json.dumps(provenance,indent=2))
        with (job/'boltz.log').open('w') as log:
            try:result=subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            except subprocess.TimeoutExpired:
                return {'ok':False,'error':'Boltz compute timeout at original 1800s budget','gpu':device,'job_id':job.name}
        if result.returncode:
            return {'ok':False,'error':'Boltz exit '+str(result.returncode),'log':(job/'boltz.log').read_text()[-5000:],'gpu':device,'job_id':job.name}
        affinity=list(out.rglob('affinity_*.json'))
        if len(affinity)!=1:raise RuntimeError('Missing or ambiguous affinity output')
        response={'ok':True,'affinity_data':json.loads(affinity[0].read_text()),'output_dir':str(affinity[0].parent),
                  'gpu':device,'gpu_host':_EXECUTION_HOST,'job_id':job.name}
        if payload.get('return_archive'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
                for p in out.rglob('*'):
                    if p.is_file():archive.write(p,p.relative_to(out))
            response['archive']=base64.b64encode(stream.getvalue()).decode()
        (job/'done.json').write_text(json.dumps({k:v for k,v in response.items() if k!='archive'},indent=2))
        return response
    finally:SLOTS.put(device)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,code,value):
        raw=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.send(200,{'status':'ok','gpu_host':_EXECUTION_HOST,'gpu_count':_GPU_COUNT,'gpu_model':_GPU_MODEL,'boltz_version':'2.2.1','cache_ready':True})
    def do_POST(self):
        try:
            if self.path!='/predict':self.send(404,{'error':'unknown route'});return
            size=int(self.headers.get('Content-Length',0));assert 0<size<=8*1024*1024
            self.send(200,predict(json.loads(self.rfile.read(size))))
        except Exception as exc:self.send(502,{'error':type(exc).__name__+': '+str(exc)[:500]})

if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',19744),Handler).serve_forever()