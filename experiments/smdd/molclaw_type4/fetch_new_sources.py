from pathlib import Path
import os,sys,json,shlex
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
local=Path(__file__).resolve().parent.parent/'deepseek-codex-type4-20261004';local.mkdir(exist_ok=True)
gpu=manage.connect('gpu');s=gpu.open_sftp()
code="""from pathlib import Path
import json
for base in ['/data2/chenfuxin/molclaw_type2_20260929','/data2/chenfuxin/smdd_type3_harness_20261001','/data2/chenfuxin/molclaw_20260924','/data2/chenfuxin/smdd_type3_transfer_20260930']:
 r=Path(base);print('BASE',base,[p.name for p in r.iterdir()] if r.exists() else None)
 for p in r.glob('**/agent_harness/agent_loop.py'):print('HARNESS',p, p.read_text().splitlines()[:25])
 for p in r.glob('*.py'):
  if 'proxy' in p.name or 'runtime' in p.name:print('FILE',p,p.stat().st_size)
"""
manage.execute(gpu,code)
for name,src in [('fourbench_run.py','/data2/chenfuxin/codex_fourbench_20261002/run.py'),('proxy_template.py','/data2/chenfuxin/codex_fourbench_20261002/launch_proxy.py')]:s.get(src,str(local/name))
s.close();gpu.close()
