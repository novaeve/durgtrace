import json,shutil,subprocess
from pathlib import Path
import run
ROOT=run.ROOT
source=Path('/data2/chenfuxin/molclaw_fourbench_20260929')
shutil.copyfile(source/'cases.json',ROOT/'cases.json')
rows=run.cases();assert len(rows)==3800 and len({c['id'] for c in rows})==3800
version=subprocess.check_output([str(run.OLD/'bin/codex'),'--version'],text=True).strip()
run.dump(ROOT/'manifest.json',{'method':'codex','cli':version,'model':run.MODEL,'temperature':0,'enable_thinking':False,'workers':2,'count':3800,'case_sha256':run.sha(ROOT/'cases.json'),'same_cases_as':str(source/'cases.json'),'reviewer':False,'memory':False,'multi_agent':False,'tools':'native Codex shell/file tools with RDKit; no MolClaw skills/SCP','limits':{'wall_seconds':3600,'idle_seconds':1800},'gold_access':'offline scorer only; hidden files not mounted','output_parser':'same unique <answer> parser as MolClaw','source_hashes':{p.name:run.sha(p) for p in ROOT.glob('*.py')},'codex_binary_sha256':run.sha(run.OLD/'bin/codex')})
print(json.dumps({'cli':version,'case_count':len(rows),'same_case_hash':run.sha(ROOT/'cases.json')==run.sha(source/'cases.json')}))
