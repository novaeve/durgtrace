"""Original evaluation, redirecting only Boltz execution to the local GPU worker."""
import json
from pathlib import Path
import runpy
import sys
import time
import uuid
import yaml
sys.path.insert(0,'/eval/code')
from metrics.boltz_manager import BoltzManager

def predict(self,yaml_path,output_dir_name='boltz_results',diffusion_samples=10):
    request=Path('/queue')/uuid.uuid4().hex;request.mkdir()
    (request/'request.json').write_text(json.dumps({'payload':yaml.safe_load(Path(yaml_path).read_text()),'samples':diffusion_samples}))
    for _ in range(1900):
        if (request/'done.json').exists():break
        time.sleep(1)
    else:raise TimeoutError('Local GPU evaluation timeout')
    result=json.loads((request/'done.json').read_text())
    if 'error' in result:raise RuntimeError(result['error'])
    job=Path(yaml_path).stem
    dest=Path(self.work_dir)/output_dir_name/('boltz_results_'+job)/'predictions'/job
    dest.mkdir(parents=True,exist_ok=True)
    (dest/f'affinity_{job}.json').write_text(json.dumps(result['affinity']))
    return str(Path(self.work_dir)/output_dir_name)

BoltzManager.run_prediction=predict
runpy.run_path('/eval/eval_entrypoint.py',run_name='__main__')
