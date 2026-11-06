from pathlib import Path
import json
import yaml
from smdd_backends import ROOT,boltz_payload

source=ROOT/'runs/full_type4_flowfix1/smdd_004_ABL1_0/oracles/boltz_18313675b2d5/input.yaml'
out=ROOT/'runs/runtimefix_preflight'
result=boltz_payload(yaml.safe_load(source.read_text()),out/'boltz_validation',gpu=0)
(out/'boltz_result.json').write_text(json.dumps({'source':str(source),'gpu':0,'parallel_samples':1,'samples':10,'result':result},indent=2))
print(json.dumps(result))
