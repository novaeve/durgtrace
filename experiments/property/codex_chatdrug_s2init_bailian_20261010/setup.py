"""Prepare a fresh, aligned 1600-case native Codex+Bailian experiment."""
import ast,collections,hashlib,json,os,shutil,sys
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
REF=Path('/data/chenfuxin/codex_chatdrug_molopt_loopguard_c16_20261010')
PREV=Path('/data2/chenfuxin/gpt6luna_agents_three_settings_20261010')
NAMES=('run.py','relay.py','legacy_relay.py','bridge.py','loop_control.py','adaptive_gate.py','process_cleanup.py')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
assert not (ROOT/'manifest.json').exists(),'Existing experiment must be inspected, not re-prepared'
ref=json.loads((REF/'manifest.json').read_text())
assert ref['model']=='deepseek-v4.1-flash' and ref['harness_variant']=='native_codex_loop_guard_v1'
for name in NAMES:
 assert sha(REF/name)==ref['source_hashes'][name],name
 shutil.copy2(REF/name,ROOT/name)
 assert sha(ROOT/name)==ref['source_hashes'][name],name
before=json.loads((PREV/'manifest.json').read_text())
assert sha(PREV/'jobs.json')==before['jobs_sha256']
assert sha(PREV/'common.py')==before['common_sha256']
shutil.copy2(PREV/'common.py',ROOT/'common.py')
jobs=[j for j in json.loads((PREV/'jobs.json').read_text()) if j['setting']=='2_s2_prompt_chatdrug']
assert len(jobs)==1600
pure=[j['case'] for j in jobs]
assert collections.Counter(c['property'] for c in pure)=={'LogP':800,'QED':800}
assert len({c['id'] for c in pure})==1600
assert sha(REF/'original_cases.json')==ref['case_sha256']
byid={c['id']:c for c in json.loads((REF/'cases.json').read_text())}
cases=[]
for c in pure:
 for k,v in c.items():
  if k!='instruction':assert byid[c['id']].get(k)==v,(c['id'],k)
 assert c['instruction']==f"Optimize the molecule {c['smiles']} to have a {c['direction']} {c['property']} value."
 assert 'similar' not in c['instruction'].lower()
 cases.append(dict(c,bench=c['benchmark'],bucket=str(c['task'])+'_'+c['constraint'],index=int(c['id'].rsplit('_',1)[1]),prompt=c['instruction']))
dump(ROOT/'jobs.json',jobs);dump(ROOT/'pure_cases.json',pure);dump(ROOT/'cases.json',cases)
sys.path.insert(0,str(ROOT))
import run as native,legacy_relay
cli=native.OLD/'bin/codex'
assert sha(cli)==ref['native_codex_binary_sha256']
credential=legacy_relay.load_credentials();url=urlsplit(credential['base_url'])
assert url.scheme=='https' and url.hostname in ('dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com','coding.dashscope.aliyuncs.com','ws-ucxu0ixh6lwfu9m0.cn-beijing.maas.aliyuncs.com') and not url.username and not url.query,'Bailian endpoint required'
from common import score
for c in pure:
 assert not score(c,c['smiles'])['success']
 assert not score(c,None)['success']
manifest={'method':'Codex','model':native.MODEL,'provider':'Bailian','provider_host':url.hostname,'provider_base_path':url.path,
 'setting':'2_s2_prompt_chatdrug','expected':1600,'properties':dict(collections.Counter(c['property'] for c in pure)),
 'workers':16,'pilot_cases':8,'harness_variant':ref['harness_variant'],'reference_root':str(REF),
 'prompt':'Byte-identical canonical S2 initialization from preceding agents. No explicit similar-molecule requirement.',
 'evaluation':'Official S2 direction only; no amplitude, Kekulize or similarity cutoff; one final submitted molecule.',
 'temperature':0,'enable_thinking':False,'reasoning_effort':None,'max_tokens':None,
 'native_budget':ref['budget'],'tools':ref['tools'],'loop_guard':ref['loop_guard'],
 'no_retained_generation_import':True,'jobs_sha256':sha(ROOT/'jobs.json'),'cases_sha256':sha(ROOT/'cases.json'),
 'common_sha256':sha(ROOT/'common.py'),'native_codex_binary':str(cli),'native_codex_binary_sha256':sha(cli),
 'frozen_harness':{name:sha(ROOT/name) for name in NAMES},'wrapper_code_hashes':{p.name:sha(p) for p in ROOT.glob('*.py') if p.name not in NAMES}}
dump(ROOT/'manifest.json',manifest)
print(json.dumps({'prepared':True,'expected':1600,'properties':manifest['properties'],'provider_host':url.hostname,'model':native.MODEL,'workers':16}),flush=True)
