import json,os,pathlib,traceback,yaml
from gpu_transport import predict
R=pathlib.Path(__file__).resolve().parent
os.environ['CHATDRUG_GPU']='6'
paths=list(R.glob('recovery_attempts/*/agentdrug/run/*/gpu_calls/call_1/input.yaml'))
assert paths
try:
 r=predict(yaml.safe_load(paths[0].read_text()),R/'boltz_smoke',10,42)
 assert 'affinity_probability_binary' in r and 'affinity_pred_value' in r
 (R/'boltz_smoke_result.json').write_text(json.dumps({'infrastructure_passed':True,'affinity':r},indent=2));print('BOLTZ_REAL_PREDICTION_PASS',flush=True)
except Exception:
 traceback.print_exc();(R/'boltz_smoke_result.json').write_text(json.dumps({'infrastructure_passed':False}));raise
