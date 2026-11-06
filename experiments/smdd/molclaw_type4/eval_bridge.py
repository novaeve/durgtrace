"""Official metric execution with only Boltz process transport redirected."""
import json,sys,time,uuid,shutil
from pathlib import Path
sys.path.insert(0,'/eval/code')
from metrics.boltz_manager import BoltzManager

def predict(self,yaml_path,output_dir_name='boltz_results',diffusion_samples=10):
 q=Path('/queue')/uuid.uuid4().hex;q.mkdir()
 shutil.copyfile(yaml_path,q/Path(yaml_path).name)
 data={'yaml_name':Path(yaml_path).name,'samples':diffusion_samples}
 tmp=q/'request.tmp';tmp.write_text(json.dumps(data));tmp.replace(q/'request.json')
 for _ in range(21600):
  if (q/'done.json').exists():break
  time.sleep(1)
 else:raise TimeoutError('GPU queue exceeded six hours')
 result=json.loads((q/'done.json').read_text())
 if result.get('error'):raise RuntimeError(result['error'])
 return str(q/'out')
BoltzManager.run_prediction=predict
from evaluator.eval_entrypoint import main
main()
