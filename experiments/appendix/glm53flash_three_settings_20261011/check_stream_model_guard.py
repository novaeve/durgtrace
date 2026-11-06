"""Model identity remains verified across missing-metadata deltas and empty usage frames."""
import ast,json
from pathlib import Path
source=Path(__file__).with_name('gateway_relay_v2.py')
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='StreamModelGuard')
ns={'MODEL':'glm-5.3-flash','json':json};exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
Guard=ns['StreamModelGuard']
# Incomplete metadata never releases text before a verified model frame arrives.
g=Guard(lambda obj:obj)
assert g.push({'choices':[],'usage':None})==[]
assert g.push({'choices':[{'delta':{'content':'C'}}]})==[]
out=g.push({'model':'glm-5.3-flash','choices':[{'delta':{'content':'CO'}}]})
assert len(out)==3 and [x['choices'][0]['delta']['content'] for x in out if x['choices']]==['C','CO']
assert out[1]['_experiment_upstream_model'] is None and out[1]['_experiment_verified_upstream_model']=='glm-5.3-flash'
# Later deltas and empty usage metadata inherit the verified identity, preserving content.
out=g.push({'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'{}'}}]}}]})
assert out[0]['choices'][0]['delta']['tool_calls'][0]['function']['arguments']=='{}'
assert g.push({'choices':[],'usage':None})[0]['model']=='glm-5.3-flash'
g.finish()
# Another explicit model is rejected even after a valid header.
try:g.push({'model':'deepseek-v4.1-flash','choices':[]})
except ValueError:pass
else:raise AssertionError('Different model accepted')
# A completion without any model verification can never be accepted.
g=Guard(lambda obj:obj);assert g.push({'choices':[{'delta':{'content':'CCO'}}]})==[]
try:g.finish()
except ValueError:pass
else:raise AssertionError('Never-verified completion accepted')
print('Stream guard passed: missing metadata preserved; text buffered until verified; different or never-verified models rejected.')
