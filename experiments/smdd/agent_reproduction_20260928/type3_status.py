import json
from pathlib import Path
ROOT=Path('/data2/chenfuxin/liddia_smdd_type3_20261004')
OUT=ROOT/'runs/full_high_v1'
status=json.loads((OUT/'batch_status.json').read_text())
finished=status.pop('finished',{})
print(json.dumps(status))
for task in sorted(OUT.glob('smdd_003*')):
    if not task.is_dir():continue
    for path in sorted((task/'api').glob('*.json'))[:1]:
        rec=json.loads(path.read_text());req=rec.get('request',{});response=rec.get('response',{})
        print(json.dumps({'task':task.name,'request':{k:req.get(k) for k in ('model','enable_thinking','reasoning_effort','temperature')},
                          'has_per_call_cap':'max_tokens' in req,'returned_model':response.get('model'),
                          'usage':response.get('usage'),'response_received':bool(response)}))
print(json.dumps({'evaluations':{label:sum(x.get('evaluation_status')==label for x in finished.values()) for label in ('passed','failed','errored')},
                  'smoke_verification':json.loads((ROOT/'smoke/verification.json').read_text())['status']}))
