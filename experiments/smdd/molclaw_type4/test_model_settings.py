"""Verify the actual request builder without API authentication or network."""
import ast,json,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
captured=[]
def post(url,json,headers,timeout):
 captured.append(json)
 return types.SimpleNamespace(status_code=200,json=lambda:{'model':'deepseek-v4.1-flash','usage':{'total_tokens':1},'choices':[{'message':{'role':'assistant','content':'ok'}}]})
tree=ast.parse((ROOT/'runtime.py').read_text())
node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='API')
ns={'Path':Path,'time':time,'dump':lambda *a:None,'requests':types.SimpleNamespace(post=post,RequestException=RuntimeError)}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<request-builder-test>','exec'),ns)
api=ns['API'].__new__(ns['API']);api.calls=0;api.total_tokens=0;api.reasoning={};api.out=ROOT;api.url='http://invalid.test';api.key='test-only'
api.complete([{'role':'user','content':'test'}],temperature=1)
assert captured[0]['model']=='deepseek-v4.1-flash'
assert captured[0]['enable_thinking'] is False
assert 'reasoning_effort' not in captured[0]
assert captured[0]['temperature']==1
assert 'max_tokens' not in captured[0]
print('PASS: request builder fixes DeepSeek V4.1 Flash, thinking=false, no reasoning_effort, temperature=1')
