"""Add native Codex and the paired direct baseline using the same frozen 4200 jobs."""
import ast,collections,hashlib,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REF=Path('/data/chenfuxin/codex_chatdrug_molopt_loopguard_c16_20261010')
CHAT=Path('/data2/chenfuxin/chatdrug_generalization_20260920')
NAMES=('run.py','relay.py','legacy_relay.py','bridge.py','loop_control.py','adaptive_gate.py','process_cleanup.py')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2))
def replace_fn(text,name,code):
 tree=ast.parse(text);n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 lines=text.splitlines(True);lines[n.lineno-1:n.end_lineno]=[code+'\n'];result=''.join(lines);ast.parse(result);return result
assert not (ROOT/'codex/manifest.json').exists() and not (ROOT/'direct/manifest.json').exists(),'Do not overwrite prepared experiments'
ref=json.loads((REF/'manifest.json').read_text());assert ref['model']=='deepseek-v4.1-flash'
source_pins={}
for name in NAMES:
 assert sha(REF/name)==ref['source_hashes'][name],name
 source_pins[str(REF/name)]=sha(REF/name)
codex=ROOT/'codex';native=codex/'native';native.mkdir(parents=True)
for name in NAMES:
 text=(REF/name).read_text().replace('deepseek-v4.1-flash','glm-5.3-flash')
 if name=='legacy_relay.py':
  text=replace_fn(text,'load_credentials',"def load_credentials():\n    return {'base_url':'http://127.0.0.1:18853/v4','api_key':'local-glm-boundary'}")
  text=replace_fn(text,'settings',"def settings(body):\n    payload=dict(body)\n    payload.update(model=MODEL,temperature=0,reasoning_effort='low',stream=True)\n    for key in ('enable_thinking','reasoning','thinking','max_tokens','max_completion_tokens','store'):\n        payload.pop(key,None)\n    return payload")
  text=text.replace("Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env')","Path('official_glm_host_gateway_no_key_in_sandbox')")
 if name=='relay.py':
  text=text.replace("'enable_thinking':False,'reasoning_effort':None","'enable_thinking':True,'reasoning_effort':'low'")
 if name=='bridge.py':
  text=text.replace("'extra_body':{'enable_thinking':False}","'extra_body':{'reasoning_effort':'low'}")
  text=text.replace("LITELLLM_LOG='ERROR'","LITELLLM_LOG='ERROR'")
  text=text.replace("LITELLM_LOG='ERROR'","LITELLM_LOG='ERROR',OPENSSL_CONF='/dev/null'")
 ast.parse(text);(native/name).write_text(text)
for method in ('codex','direct'):
 directory=ROOT/method;directory.mkdir(exist_ok=True)
 shutil.copy2(ROOT/'agents/jobs.json',directory/'jobs.json')
 shutil.copy2(ROOT/'agents/common.py',directory/'common.py')
 jobs=json.loads((directory/'jobs.json').read_text());assert len(jobs)==4200
 assert collections.Counter(j['setting'] for j in jobs)=={'1_original_chatdrug':1600,'2_s2_prompt_chatdrug':1600,'3_original_s2':1000}
 m={'model':'glm-5.3-flash','method':'Codex' if method=='codex' else 'GLM_direct','expected':4200,'settings':dict(collections.Counter(j['setting'] for j in jobs)),
    'jobs_sha256':sha(directory/'jobs.json'),'common_sha256':sha(directory/'common.py'),
    'provider':'Official GLM via existing 32-request shared gateway; real API key stays on CPU host',
    'reasoning_effort':'low','temperature':0,
    'evaluation':'Same official S2 mol_prop strict direction only; no amplitude, no similarity cutoff, no Kekulize; one final parsed molecule',
    'initialization':'Byte-identical jobs and instructions to preceding five GLM methods',
    'created':time.time()}
 if method=='codex':
  m.update(workers=16,native_cli=ref['cli'],cli_binary=ref.get('native_codex_binary', '/data2/chenfuxin/smdd_codex_type2_bailian_20260929/bin/codex'),
   cli_sha256=ref['native_codex_binary_sha256'],reference_roots=[str(REF),'/data/chenfuxin/codex_chatdrug_s2init_bailian_20261010'],
   source_pins=source_pins,native_budget=ref['budget'],loop_guard=ref['loop_guard'],native_tools=ref['tools'],
   reviewer=False,memory=False,multi_agent=False,max_tokens=None,
   transport_changes='Only GLM model/provider settings; native Responses-to-Chat bridge, shell/file tools, isolation and loop guard retained',
   documentation='https://learn.chatgpt.com/docs/config-file/config-advanced')
  binary=Path(m['cli_binary']);assert sha(binary)==m['cli_sha256'],'Frozen Codex binary changed'
  m['code_hashes']={str(p.relative_to(directory)):sha(p) for p in directory.rglob('*.py')}
 else:
  m.update(workers=0,max_tokens=2048,logical_calls_per_case=1,
   reference_roots=['/data2/chenfuxin/molopt_original_bailian_20261007','/data2/chenfuxin/chatdrug_prompt_aligned_bailian_20261006'],
   paired_source=str(ROOT/'agents/native/ChatDrug'),
   generation_policy='As in DeepSeek_direct, use the actual shared_initial model response from the paired ChatDrug run. No feedback, tools, new generation, repeated sample or property-based candidate selection.',
   parser='Frozen ChatDrug pilot.parse_candidate / upstream SM.parse_molecule',
   output_policy='Original baseline requests five bullet-point SMILES; original similarity parser selects exactly one final molecule; do not select using target-property scores.',
   frozen_dependencies={str(CHAT/'pilot.py'):sha(CHAT/'pilot.py'),str(CHAT/'upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py'):sha(CHAT/'upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py')})
 dump(directory/'manifest.json',m)
dump(ROOT/'expanded_experiment.json',{'model':'glm-5.3-flash','methods':['ChatDrug','AgentDrug','MolLingo','MolClaw','SoL-Pi','Codex','GLM_direct'],'expected_per_method':4200,'expected_total':29400,'new_generation':'Codex 4200; paired direct derives 4200 already recorded first-generation responses without duplicate API charges'})
print('PREPARED_CODEX_AND_PAIRED_DIRECT_4200_EACH',flush=True)
