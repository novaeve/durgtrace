"""Inside original evaluator image: move only Boltz execution to GPU host."""
import json,os,pathlib,runpy,shutil,sys,time,uuid
sys.path.insert(0,'/eval/code')
from metrics.boltz_manager import BoltzManager

def remote_prediction(self,yaml_path,output_dir_name='boltz_results',diffusion_samples=10):
    import yaml
    token=uuid.uuid4().hex;root=pathlib.Path('/queue')/token;root.mkdir()
    owner=pathlib.Path('/queue').stat();os.chown(root,owner.st_uid,owner.st_gid)
    (root/'request.json').write_text(json.dumps({'payload':yaml.safe_load(pathlib.Path(yaml_path).read_text()),'samples':diffusion_samples}))
    for _ in range(1900):
        if (root/'done.json').exists():break
        time.sleep(1)
    else:raise TimeoutError('GPU evaluation queue timeout')
    result=json.loads((root/'done.json').read_text())
    if 'error' in result:raise RuntimeError(result['error'])
    job=pathlib.Path(yaml_path).stem
    dest=pathlib.Path(self.work_dir)/output_dir_name/('boltz_results_'+job)/'predictions'/job
    dest.mkdir(parents=True,exist_ok=True)
    (dest/f'affinity_{job}.json').write_text(json.dumps(result['affinity']))
    return str(pathlib.Path(self.work_dir)/output_dir_name)

BoltzManager.run_prediction=remote_prediction
runpy.run_path('/eval/eval_entrypoint.py',run_name='__main__')
