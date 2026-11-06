import json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MOL=Path('/data2/chenfuxin/molclaw_20260924')
source=Path('/data2/chenfuxin/molclaw_type2_20260929/run.py')
shutil.copyfile(source,ROOT/'native_transport_source.py')
proxy=(MOL/'launch_proxy.py').read_text()
proxy=proxy.replace("'extra_body':{'enable_thinking':False}","'temperature':0,'extra_body':{'enable_thinking':False}")
proxy=proxy.replace("str(ROOT/'isolated_env/bin/litellm')","str(pathlib.Path('/data2/chenfuxin/molclaw_20260924/isolated_env/bin/litellm'))")
proxy=proxy.replace("'18745'","'18749'")
(ROOT/'launch_proxy.py').write_text(proxy)
import run
rows=run.cases()
run.dump(ROOT/'cases.json',rows)
refs=[run.S2/'data/manifest.json',run.S2/'source/manifest.json',run.LANG/'data/experiment_manifest.json',run.LANG/'data/cases.json']
run.dump(ROOT/'manifest.json',{'model':run.MODEL,'temperature':0,'enable_thinking':False,'workers':2,'mode':'native MolClaw both','counts':dict(__import__('collections').Counter(c['bench'] for c in rows)),'references':{str(p):run.sha(p) for p in refs},'sources':{p.name:run.sha(p) for p in ROOT.glob('*.py')},'mollang_comparator':'no_rules_v2 for ChatDrug/AgentDrug; original direct DeepSeek','gold_access':'offline score.py only; not mounted into native workspace','format_adaptation':'MolLang <smiles> to native <answer>; single native final answer','idle_timeout_seconds':1800,'upstream_skill_hashes':{str(p.relative_to(MOL/'source/MolClaw-main/skills')):run.sha(p) for p in (MOL/'source/MolClaw-main/skills').rglob('*') if p.is_file()}})
print(json.dumps({'prepared':len(rows),'counts':dict(__import__('collections').Counter(c['bench'] for c in rows))}))
