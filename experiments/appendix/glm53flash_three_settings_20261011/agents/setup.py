"""Freeze the exact three DeepSeek reference configurations and their S2 rescoring."""
import ast,collections,copy,hashlib,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/data2/chenfuxin')
CHAT=BASE/'chatdrug_generalization_20260920'
ORIGINAL=BASE/'molopt_original_bailian_20261007'
ALIGNED=BASE/'chatdrug_prompt_aligned_bailian_20261006'
PINS={
 CHAT/'full_case.py':'76bbb86f1f9a299a77646611f273d32db319f69a17c4491f013801721830d45f',
 CHAT/'full_experiment.py':'0998f12f5f4da4910606d6c2aca85befe91103775c7b9f64793fea99dbf7375d',
 CHAT/'pilot.py':'0294a4125863744543545e9de6c7665646f17ba7442c1c4d6926fb856ba52331',
 CHAT/'deepseek_check.py':'bc3de4735708ab814b38637aa038b503c7f56abc7745902785e9788fd71d18de',
 BASE/'agentdrug_20260922/runner.py':'24aee817f4293dac507fcd66cadd5755aea290c48df968ba042d1d3a227b571c',
 BASE/'agentdrug_20260922/core_fixed.py':'27ea4dba5b24106e8ad60f42826ef7d554d523385710fb41005aa282372dfb9d'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (ROOT/'runs').exists() and not (ROOT/'manifest.json').exists(),'Never overwrite an existing experiment'
for p,h in PINS.items():assert sha(p)==h,str(p)
shutil.copy2(BASE/'molecule_s2_prompt_eval_20261007/common.py',ROOT/'common.py')
original=json.loads((ORIGINAL/'cases.json').read_text())
aligned=json.loads((ALIGNED/'cases.json').read_text())
groups={
 '1_original_chatdrug':[c for c in original if c['benchmark']=='ChatDrug' and c['task'] in (101,102,103,104)],
 '2_s2_prompt_chatdrug':[c for c in aligned if c['task'] in (101,102,103,104)],
 '3_original_s2':[c for c in original if c['benchmark']=='S2-mini' and c['property'] in ('LogP','QED')]}
assert [len(c) for c in groups.values()]==[1600,1600,1000]
original_by_id={c['id']:c for c in groups['1_original_chatdrug']}
for c in groups['1_original_chatdrug']:assert 'The output molecule should be similar to the input molecule.' in c['instruction']
for c in groups['2_s2_prompt_chatdrug']:
 before=original_by_id[c['id']]
 assert {k:v for k,v in before.items() if k!='instruction'}=={k:v for k,v in c.items() if k!='instruction'}
 assert c['instruction']==f"Optimize the molecule {c['smiles']} to have a {c['direction']} {c['property']} value."
 assert 'similar' not in c['instruction'].lower()
jobs=[{'setting':s,'case':c} for s,cc in groups.items() for c in cc]
assert len(jobs)==len({(j['setting'],j['case']['id']) for j in jobs})==4200
(ROOT/'jobs.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2))
tree=ast.parse((CHAT/'full_case.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case')
body=next(n for n in fn.body if isinstance(n,ast.Try))
start=next(i for i,n in enumerate(body.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='independent' for t in n.targets))
end=next(i for i,n in enumerate(body.body) if ast.unparse(n)=="result['status'] = 'complete'")
body.body=body.body[:start]+body.body[end:]
module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
(ROOT/'chat_native.py').write_text(ast.unparse(module)+'\n')
(ROOT/'private').mkdir(mode=0o700,exist_ok=True)
shutil.copy2(BASE/'gpt_s2_direct_20261009/private/chatgpt.env',ROOT/'private/chatgpt.env')
os.chmod(ROOT/'private',0o700);os.chmod(ROOT/'private/chatgpt.env',0o600)
manifest=dict(model='glm-5.3-flash',provider='tok.fan; previously user-authorized key',methods=['ChatDrug','AgentDrug'],
 expected_per_method=4200,expected_total=8400,workers_total=8,temperature=0,reasoning_effort='low',
 settings={s:dict(count=len(cc),properties=dict(collections.Counter(c['property'] for c in cc)),reference_root=str(ALIGNED if s.startswith('2_') else ORIGINAL)) for s,cc in groups.items()},
 initialization='Exact copied DeepSeek reference case dictionaries; setting2 changes only to its existing canonical S2 initialization template.',
 online_policy='Preserve native ChatDrug/AgentDrug parsers, retrieval, feedback, stopping, validity handling, original thresholds and source Kekulize. S2 cases retain their native S2 initialization.',
 final_evaluation='All three settings use official S2 descriptors without Kekulize; strict direction only; no amplitude or similarity cutoff; one final agent-selected molecule.',
 caps={'ChatDrug':2048,'AgentDrug':256},chatdrug_rounds=3,agentdrug_refine_steps_single=3,
 discarded_unrequested_arm='Independent-three postprocessing removed after native ChatDrug final output; shared first-response metadata retained without extra calls.',
 pilot='20 cases per agent: 8 original source, 8 aligned source, 4 S2 direction/property representatives; reuse in full.',
 jobs_sha256=sha(ROOT/'jobs.json'),common_sha256=sha(ROOT/'common.py'),native_chat_sha256=sha(ROOT/'chat_native.py'),
 frozen_dependencies={str(p):h for p,h in PINS.items()},
 retrieval_sha256=sha(CHAT/'prepared_full/retrieval.csv'),
 code_hashes={p.name:sha(p) for p in ROOT.glob('*.py')})
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
from common import score
references=[]
for method in manifest['methods']:
 for setting,cc in groups.items():
  counts=collections.defaultdict(collections.Counter)
  root=ALIGNED if setting.startswith('2_') else ORIGINAL
  for c in cc:
   old=json.loads((root/'runs'/method/c['id']/'result.json').read_text())
   assert old['case']==c
   result=score(c,old.get('candidate') if old['status']=='complete' else None)
   counts[c['property']]['expected']+=1;counts[c['property']]['success']+=result['success']
   if setting.startswith('3_'):assert result['success']==bool(old['status']=='complete' and old['score']['success'])
  for prop,count in counts.items():references.append(dict(method=method,setting=setting,property=prop,**count,rate=count['success']/count['expected']))
expected={
 ('ChatDrug','1_original_chatdrug','LogP'):629,('ChatDrug','1_original_chatdrug','QED'):585,
 ('AgentDrug','1_original_chatdrug','LogP'):580,('AgentDrug','1_original_chatdrug','QED'):672,
 ('ChatDrug','2_s2_prompt_chatdrug','LogP'):701,('ChatDrug','2_s2_prompt_chatdrug','QED'):570,
 ('AgentDrug','2_s2_prompt_chatdrug','LogP'):607,('AgentDrug','2_s2_prompt_chatdrug','QED'):663,
 ('ChatDrug','3_original_s2','LogP'):431,('ChatDrug','3_original_s2','QED'):391,
 ('AgentDrug','3_original_s2','LogP'):421,('AgentDrug','3_original_s2','QED'):448}
assert all(r['success']==expected[(r['method'],r['setting'],r['property'])] for r in references)
(ROOT/'deepseek_reference_s2.json').write_text(json.dumps(references,indent=2))
print(json.dumps({'prepared':True,'per_agent':4200,'total':8400,'deepseek_reference_rescoring_verified':True}))
