import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
os.environ.setdefault('SMDD_CPU_PASSWORD','123')
code='''import pathlib,json
root=pathlib.Path(ROOTPATH)
keys={'model','enable_thinking','reasoning_effort','temperature','max_tokens','thinking','effort'}
def walk(x,prefix=''):
 if isinstance(x,dict):
  for k,v in x.items():
   if k in keys and (not isinstance(v,(dict,list)) or k=='thinking'):print(prefix+k,repr(v)[:200])
   if isinstance(v,dict):walk(v,prefix+k+'.')
 elif isinstance(x,list):
  for v in x[-1:]:walk(v,prefix)
for method in METHODS:
 base=root/method if method else root
 print('METHOD',method or 'liddia')
 configs=list(base.glob('**/protocol.json'))[:1]+list(base.glob('**/run_config.json'))[:1]
 requests=list(base.glob('**/llm_calls.json'))
 requests=sorted(requests,key=lambda p:p.stat().st_mtime,reverse=True)[:2]
 for p in configs+requests:
  print('FILE',p);data=json.loads(p.read_text());walk(data[-1] if isinstance(data,list) else data)
 if not requests:
  print('CANDIDATE_LOGS',[(str(p.relative_to(base)),p.stat().st_size) for p in base.glob('run/*/*') if p.is_file() and p.suffix in ['.json','.jsonl']][:12])
 if method:
  for p in list(root.glob('*.py'))+list((root/'harness').glob('*.py')):
   if p.exists():
    for line in p.read_text().splitlines():
     if any(k in line for k in ['enable_thinking','reasoning_effort','deepseek-v4']) and not any(k in line.lower() for k in ['api_key','authorization','password']):print('SOURCE',p.name,line[:300])
'''
for host,root,methods in [('cpu',manage.CPU,['chatdrug','agentdrug']),('gpu','/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3',[''])]:
 c=manage.connect(host)
 manage.execute(c,code.replace('ROOTPATH',repr(root)).replace('METHODS',repr(methods)))
 c.close()
