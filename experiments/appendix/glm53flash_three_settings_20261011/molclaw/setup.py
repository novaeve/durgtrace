"""Copy the frozen MolClaw both-mode runner for the exact preceding three settings."""
import ast,collections,hashlib,json,os,shutil,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/data2/chenfuxin')
CLAW=BASE/'molclaw_20260924'
PREV=BASE/'gpt6luna_agents_three_settings_20261010'
ALIGNED=BASE/'molecule_s2_prompt_eval_20261007'
assert not (ROOT/'manifest.json').exists(),'Never overwrite an existing prepared experiment'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2))
def replace(text,old,new):
 assert text.count(old)==1,old
 return text.replace(old,new,1)
pins={CLAW/'smoke_agent.py':'8c8851b4a09cea456e6f3ccffb87edb205d77022feb4bba789c943dc3c942336',
 CLAW/'benchmark_runner.py':'efe9e5c34b734a742a6dbebe81a216f5a9cc0c431dd8b7ba7de4b9a04e5b74ce',
 CLAW/'launch_proxy.py':'bde07350e22c4e9f7bb1b69a0db6def52bd41c8f0a3e79053ba3485c948c2d06',
 CLAW/'source/MolClaw-main/molclaw_run/infer/claude_agent/run_claude.py':'6dbe18799953e03b58ab6cfed96008a0164c6d0da42726255e0706ef88ba30b1'}
for p,h in pins.items():assert sha(p)==h,str(p)
previous=json.loads((PREV/'manifest.json').read_text());assert sha(PREV/'jobs.json')==previous['jobs_sha256']
shutil.copy2(PREV/'jobs.json',ROOT/'jobs.json');shutil.copy2(PREV/'common.py',ROOT/'common.py')
jobs=json.loads((ROOT/'jobs.json').read_text());assert len(jobs)==4200
for setting in ('1_original_chatdrug','2_s2_prompt_chatdrug','3_original_s2'):
 cc=[j['case'] for j in jobs if j['setting']==setting]
 assert len(cc)==(1000 if setting.startswith('3_') else 1600)
 assert len({c['id'] for c in cc})==len(cc)
 dump(ROOT/'inputs'/setting/'cases.json',cc)
port=None
for candidate in (18746,18747,18748,18749):
 with socket.socket() as s:
  try:s.bind(('127.0.0.1',candidate));port=candidate;break
  except OSError:pass
assert port is not None
dump(ROOT/'proxy_port.json',{'port':port})
text=(CLAW/'smoke_agent.py').read_text()
text=replace(text,'ROOT=pathlib.Path(__file__).resolve().parent',f'ROOT=pathlib.Path({str(CLAW)!r})\nEXP=pathlib.Path({str(ROOT)!r})')
text=replace(text,"pathlib.Path('/data2/chenfuxin/chatdrug_generalization_20260920/prepared_full/cases.json')","(EXP/'inputs'/sys.argv[1]/'cases.json')")
text=replace(text,"out=ROOT/'runs'/stage/case['id']","out=EXP/'native/MolClaw'/stage/case['id']")
text=replace(text,"metadata=ROOT/'case_manifests'/stage","metadata=EXP/'case_manifests'/stage")
text=text.replace('http://127.0.0.1:18745',f'http://127.0.0.1:{port}').replace('deepseek-v4.1-flash','glm-5.3-flash')
text=replace(text,"env['CLAUDE_CONFIG_DIR']=str(out/'.runtime')","env['CLAUDE_CONFIG_DIR']=str(out/'.runtime')\nenv['ANTHROPIC_CUSTOM_HEADERS']='X-MolClaw-Case: '+stage+'/'+case['id']")
ast.parse(text);(ROOT/'claw_agent.py').write_text(text)
text=(CLAW/'benchmark_runner.py').read_text()
text=replace(text,'ROOT=pathlib.Path(__file__).resolve().parent','ROOT=pathlib.Path(__file__).resolve().parent\nfrom common import score')
text=replace(text,"out=ROOT/'runs'/stage/case['id']","out=ROOT/'native/MolClaw'/stage/case['id']")
text=replace(text,"str(ROOT/'smoke_agent.py')","str(ROOT/'claw_agent.py')")
text=text.replace('benchmark.score(case,','score(case,')
ast.parse(text);(ROOT/'claw_native.py').write_text(text)
(ROOT/'private').mkdir(mode=0o700,exist_ok=True)
shutil.copy2(PREV/'private/chatgpt.env',ROOT/'private/chatgpt.env')
os.chmod(ROOT/'private',0o700);os.chmod(ROOT/'private/chatgpt.env',0o600)
from common import score
for j in jobs:
 assert not score(j['case'],j['case']['smiles'])['success']
 assert not score(j['case'],None)['success']
references=[]
for setting in ('1_original_chatdrug','2_s2_prompt_chatdrug','3_original_s2'):
 parent=ALIGNED/'runs/MolClaw' if setting.startswith('2_') else CLAW/'runs/full'
 counts=collections.defaultdict(collections.Counter)
 for j in jobs:
  if j['setting']!=setting:continue
  c=j['case'];p=parent/c['id']/'result.json'
  if not p.exists():counts[c['property']]['missing_reference']+=1;continue
  row=json.loads(p.read_text());counts[c['property']]['processed']+=1
  counts[c['property']]['success']+=score(c,row.get('candidate') if row['status']=='complete' else None)['success']
 references.append({'setting':setting,'root':str(parent),'properties':counts,
  'prompt_comparable':not setting.startswith('2_'),
  'note':'Reference aligned MolClaw uses five S2 wording variants; current setting2 matches the preceding GPT6-luna agents canonical initializer.' if setting.startswith('2_') else 'Original task instruction reused.'})
dump(ROOT/'deepseek_reference_s2.json',references)
manifest={'model':'glm-5.3-flash','method':'MolClaw','expected':4200,'settings':dict(collections.Counter(j['setting'] for j in jobs)),
 'mode':'both','workers':4,'initialization':'Byte-identical to preceding GPT6-luna agent three-setting jobs.',
 'evaluation':'Official S2 descriptors; no Kekulize, amplitude or similarity cutoff; score one final answer only.',
 'native_runtime':'Frozen Claude Code, original upstream both-mode prompt builder, skills and strict SCP MCP config; native turn/token policies retained.',
 'provider':'Separate loopback LiteLLM proxy to previously user-authorized tok.fan key; primary and lightweight Claude CLI models all glm-5.3-flash.',
 'reasoning_effort':'low','temperature':'Native CLI value retained; not overridden.',
 'proxy_port':port,'jobs_sha256':sha(ROOT/'jobs.json'),'common_sha256':sha(ROOT/'common.py'),
 'frozen_dependencies':{str(p):h for p,h in pins.items()},
 'code_hashes':{p.name:sha(p) for p in ROOT.glob('*.py')},
 'reference_prompt_note':'Setting2 historical DeepSeek reference has five cycled S2 variants, current experiment uses preceding GPT6-luna uniform initialization.'}
dump(ROOT/'manifest.json',manifest)
print(json.dumps({'prepared':True,'expected':4200,'proxy_port':port}),flush=True)
