"""Prepare frozen native MolLingo/SoL-Pi with the preceding six-run inputs."""
import ast,collections,hashlib,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/data2/chenfuxin')
PREV=BASE/'gpt6luna_agents_three_settings_20261010'
LINGO=BASE/'molingo_20260922'
ALIGNED=BASE/'molecule_s2_prompt_eval_20261007'
SOL_ORIG=Path('/data/chenfuxin/sol_pi_chatdrug_molopt_20261007')
assert not (ROOT/'manifest.json').exists(),'Do not replace a prepared experiment'
assert SOL_ORIG.exists(),str(SOL_ORIG)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
dump=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2))
def replace(text,old,new):
 assert text.count(old)==1,old
 return text.replace(old,new,1)
previous=json.loads((PREV/'manifest.json').read_text())
assert sha(PREV/'jobs.json')==previous['jobs_sha256']
shutil.copy2(PREV/'jobs.json',ROOT/'jobs.json')
shutil.copy2(PREV/'common.py',ROOT/'common.py')
jobs=json.loads((ROOT/'jobs.json').read_text())
assert len(jobs)==4200
pins={LINGO/'runner.py':'b41ff5c2d3c1dba300458e38b9ae6349021034262abe6d6a6354549fe440ad37',
 LINGO/'core_fixed.py':'78d235f592f6972d818da496e3c8e0b4b0d06c6df1ccf23c58aa46d7e69e2edd',
 LINGO/'single_bailian_runner.py':'a8fb08a50f21233135f3f1248fe26c67cc1315a8c71f24511060622d5a6a9b2f'}
for p,h in pins.items():assert sha(p)==h,str(p)
text=(LINGO/'single_bailian_runner.py').read_text()
text=replace(text,'from bailian_relay import Relay,MODEL','from lingo_relay import Relay,MODEL\nfrom common import ROOT,score')
text=replace(text,"out=r.ROOT/'runs'/('single_bailian_'+stage)/case['id']","out=ROOT/'native/MolLingo'/stage/case['id']")
text=text.replace('r.benchmark.score(case,','score(case,')
ast.parse(text);(ROOT/'lingo_native.py').write_text(text)
sol=ROOT/'sol_pi';sol.mkdir()
source=SOL_ORIG/'run.py'
text=source.read_text().replace('mol-edit-deepseek','mol-edit-glm53flash')
assert 'query = case[\'instruction\']' in text
ast.parse(text);(sol/'run.py').write_text(text)
shutil.copy2(SOL_ORIG/'relay.py',sol/'frozen_relay.py')
shutil.copy2(ROOT/'sol_relay.py',sol/'relay.py')
shutil.copytree(SOL_ORIG/'bridge',sol/'bridge',ignore=shutil.ignore_patterns('node_modules'))
for p in (sol/'bridge').glob('*.ts'):
 text=p.read_text().replace('mol-edit-deepseek','mol-edit-glm53flash').replace('deepseek-v4.1-flash','glm-5.3-flash').replace('DeepSeek v4.1 Flash','GPT 6 Luna')
 p.write_text(text)
(sol/'bridge/node_modules').symlink_to('/opt/sol-pi/node_modules',target_is_directory=True)
for p in [SOL_ORIG/'run.py',SOL_ORIG/'relay.py',*list((SOL_ORIG/'bridge').glob('*.ts'))]:
 pins[p]=sha(p)
native_manifest=json.loads((ALIGNED/'manifest.json').read_text())
sol_source_pins=native_manifest['sol_source_hashes']
for name,h in sol_source_pins.items():
 p=BASE/'SoL-Pi'/name
 assert sha(p)==h,str(p)
 pins[p]=h
for j in jobs:
 c=j['case']
 assert c['property'] in ('LogP','QED')
 if j['setting'].startswith('2_'):assert c['instruction']==f"Optimize the molecule {c['smiles']} to have a {c['direction']} {c['property']} value."
(ROOT/'private').mkdir(mode=0o700)
shutil.copy2(PREV/'private/chatgpt.env',ROOT/'private/chatgpt.env')
os.chmod(ROOT/'private',0o700);os.chmod(ROOT/'private/chatgpt.env',0o600)
(ROOT/'cache/structures').mkdir(parents=True)
if (LINGO/'cache/names.json').exists():shutil.copy2(LINGO/'cache/names.json',ROOT/'cache/names.json')
shutil.copytree(LINGO/'cache/structures',ROOT/'cache/structures',dirs_exist_ok=True)
from common import score
for j in jobs:
 assert not score(j['case'],j['case']['smiles'])['success']
 assert not score(j['case'],None)['success']
references=[]
for method in ('MolLingo','SoL-Pi'):
 for setting in ('1_original_chatdrug','2_s2_prompt_chatdrug','3_original_s2'):
  cc=[j['case'] for j in jobs if j['setting']==setting];counter=collections.defaultdict(collections.Counter);mismatch=0
  if setting.startswith('2_'):parent=ALIGNED/'runs'/method
  elif method=='MolLingo':parent=LINGO/'runs/single_bailian_full'
  else:parent=SOL_ORIG/'runs/full'
  for c in cc:
   p=parent/c['id']/'result.json'
   if not p.exists():
    counter[c['property']]['missing_reference']+=1;continue
   r=json.loads(p.read_text())
   if r.get('case') and r['case']['instruction']!=c['instruction']:mismatch+=1
   ss=score(c,r.get('candidate') if r.get('status')=='complete' else None)
   counter[c['property']]['processed']+=1;counter[c['property']]['success']+=ss['success']
  references.append(dict(method=method,setting=setting,root=str(parent),properties=counter,
    comparable_prompt=not setting.startswith('2_'),prompt_policy='Reference setting2 uses five S2 variants; this run uses the preceding ChatDrug/AgentDrug canonical S2 initializer.',
    detected_instruction_mismatches=mismatch))
dump(ROOT/'deepseek_reference_s2.json',references)
manifest=dict(model='glm-5.3-flash',methods=['MolLingo','SoL-Pi'],expected_per_method=4200,expected_total=8400,
 settings=dict(collections.Counter(j['setting'] for j in jobs)),jobs_sha256=sha(ROOT/'jobs.json'),
 evaluation='Exact preceding official S2 descriptor scoring; no Kekulize, amplitude or similarity cutoff; one final submitted molecule only.',
 initialization='Byte-identical cases and initialization to preceding GPT6-luna ChatDrug/AgentDrug six experiments.',
 native_policy='MolLingo original variants=3 block assembly plus model-only final selection; SoL-Pi all four native mechanisms, original tools and episode budgets.',
 temperature=0,reasoning_effort='low',max_completion_tokens='omitted for both methods as in their native DeepSeek reference',
 workers={'MolLingo':4,'SoL-Pi':4},provider='Previously authorized tok.fan key; never exposed to agent sandbox',
 frozen_dependencies={str(p):h for p,h in pins.items()},code_hashes={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*.py')},
 reference_prompt_note='DeepSeek setting2 existing MolLingo/SoL-Pi reference has five cycled S2 wording variants rather than the canonical template from the preceding six experiments.')
dump(ROOT/'manifest.json',manifest)
print(json.dumps({'prepared':True,'per_method':4200,'total':8400,'native_sources_verified':True}),flush=True)
