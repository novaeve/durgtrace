from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
c=manage.connect('gpu')
manage.execute(c,"""from pathlib import Path
import json
import os
for p in Path('/proc').glob('[0-9]*'):
 try:
  if p.stat().st_uid!=os.getuid():continue
  args=(p/'cmdline').read_bytes().decode().split(chr(0))
  if any('run_liddia' in a or 'liddia_flow' in a for a in args):print('LIDDIA_SCRIPTS',[a for a in args if a.endswith('.py')], 'CWD',(p/'cwd').resolve())
 except (OSError,UnicodeError):pass
roots=[Path('/data2/chenfuxin/smdd_type4_full340_bailian_20260929'),Path('/data2/chenfuxin/liddia_smdd_type4_20260928')]
for root in roots:
 print('PYTHON_DIRS',[str(p.relative_to(root)) for p in root.glob('*') if p.is_dir()])
 if (root/'adapter').exists():print('ADAPTER_FILES',[str(p.relative_to(root)) for p in (root/'adapter').glob('*')])
 paths=list(root.glob('*.py'))+list(root.glob('runs/full_type4_parallel3/source/*.py'))
 for p in paths:
  lines=p.read_text().splitlines()
  for i,line in enumerate(lines):
   if any(k in line for k in ['enable_thinking','reasoning_effort','deepseek-v4']) and not any(k in line.lower() for k in ['api_key','authorization','password']): print(str(p),i+1,line[:300])
r=roots[1]/'runs/full_type4_parallel3'
p=next(r.glob('*/llm_calls.json'))
d=json.loads(p.read_text());print('LLM_LOG_SHAPE',type(d).__name__)
if isinstance(d,list):print('ITEM_KEYS',list(d[0]) if isinstance(d[0],dict) else type(d[0]).__name__)
else:print('ROOT_KEYS',list(d))
print('PROTOCOL',next(r.glob('*/protocol.json')).read_text())
""")
c.close()
