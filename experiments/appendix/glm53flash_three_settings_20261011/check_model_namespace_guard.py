"""Check exact model-family acceptance without loading any credentials or gateway."""
import ast,collections,hashlib,io,json,re,threading
from pathlib import Path
source=Path(__file__).with_name('gateway_relay_v2.py')
tree=ast.parse(source.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='canonicalize_model')
class Sink:
 def __truediv__(self,name):return self
 def open(self,*args):return io.StringIO()
import time
ns={'MODEL':'glm-5.3-flash','ROOT':Sink(),'condition':threading.Condition(),'stats':collections.Counter(),
    'BASE':'https://tok.fan/v1','PROVIDER_EPOCH':'check','re':re,'json':json,'hashlib':hashlib,'time':time}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
request={'model':'glm-5.3-flash','messages':[{'role':'user','content':'probe'}]}
good=['glm-5.3-flash','glm-5-3-flash-260828','z-ai/glm-5.3-flash','cbcn/glm-5.3-flash','new_channel/glm-5.3-flash','vendor/glm-5-3-flash-260828']
bad=[None,'glm-5.3','deepseek-v4.1-flash','vendor/qwen3','vendor/glm-5.3-flash-extra','vendor/glm-5.3-flash:thinking','vendor/vendor/glm-5.3-flash','../glm-5.3-flash','glm-5-3-flash-260829']
for label in good:
 obj=ns['canonicalize_model']({'model':label},request,set());assert obj['model']=='glm-5.3-flash',label
 if label!='glm-5.3-flash':assert obj['_experiment_upstream_model']==label
for label in bad:
 obj=ns['canonicalize_model']({'model':label},request,set());assert obj['model']!='glm-5.3-flash',label
print('Model guard passed: 6 exact-model aliases accepted, 9 other/invalid identifiers rejected; original alias labels retained.')
