from pathlib import Path
import sys,json
LOCAL=Path(__file__).resolve().parent
sys.path.insert(0,str(LOCAL.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();s=c.open_sftp();root='/yimin/zlc/sol_pi_type4_20261004'
s.put(str(LOCAL.parent/'deepseek-codex-type4-20261004/public_tasks.json'),root+'/public_tasks.json')
remote.py(c,"""from pathlib import Path
import json,shutil
r=Path('/yimin/zlc/sol_pi_type4_20261004');mol=Path('/yimin/zlc/molclaw_type4_20261003')
for name in ['tasks','public_inputs']:
 p=r/name
 if p.is_symlink():p.unlink()
 p.mkdir(exist_ok=True)
for name in ['preflight','bridge','runs']: (r/name).mkdir(exist_ok=True)
rows=json.loads((r/'public_tasks.json').read_text())
for row in rows:
 tid=row['id'];src=mol/'tasks'/tid
 (r/'tasks'/f'{tid}.json').write_text(json.dumps(row));public=r/'public_inputs'/tid;public.mkdir(exist_ok=True)
 for name in ['complex.pdb','reference.sdf']:shutil.copy2(src/name,public/name)
assert len(rows)==340;(r/'public_tasks.json').write_text(json.dumps(rows,indent=2))
print('A100 340 public-only task inputs ready')
""")
for p in (LOCAL/'a100').glob('*.py'):
 compile(p.read_text(),p.name,'exec');s.put(str(p),root+'/'+p.name)
s.put(str(LOCAL/'bridge/smdd.ts'),root+'/bridge/smdd.ts')
remote.py(c,"""from pathlib import Path
import sys,json
r=Path('/yimin/zlc/sol_pi_type4_20261004');sys.path.insert(0,str(r/'upstream'));from agent_harness.prompts import TOOL_SCHEMAS
(r/'bridge/tool_schemas.json').write_text(json.dumps(TOOL_SCHEMAS,indent=2))
assert "'enable_thinking':False" in (r/'runtime.py').read_text()
print('Model configured non-thinking on A100; no API secret transferred or printed')
""")
s.close();c.close()
