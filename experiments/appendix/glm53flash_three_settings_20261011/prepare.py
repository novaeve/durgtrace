"""Migrate frozen native runners; only paths, provider and worker allocation change."""
import ast, collections, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime'
CPU_PY=Path('/home/chenfuxin/smdd-migration/tools/py310/bin/python')
MODEL='glm-5.3-flash'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert (ROOT/'transfer.json').exists(),'Transfer must finish first'
assert not (ROOT/'prepared.json').exists(),'Already prepared'
(ROOT/'runtime_source/data2/chenfuxin').rename(RUNTIME)
(ROOT/'runtime_source/opt/codex-node').rename(ROOT/'node')
(ROOT/'bin').mkdir(exist_ok=True)
shutil.copy2(ROOT/'runtime_source/usr/bin/bwrap',ROOT/'bin/bwrap')
mapping={
 '/data2/chenfuxin/gpt6luna_agents_three_settings_20261010':str(ROOT/'agents'),
 '/data2/chenfuxin/gpt6luna_lingo_sol_three_settings_20261010':str(ROOT/'lingo_sol'),
 '/data2/chenfuxin/gpt6luna_molclaw_three_settings_20261010':str(ROOT/'molclaw'),
 '/data2/chenfuxin':str(RUNTIME),
}
for source,target in [('gpt6luna_agents_three_settings_20261010','agents'),('gpt6luna_lingo_sol_three_settings_20261010','lingo_sol'),('gpt6luna_molclaw_three_settings_20261010','molclaw')]:
 (RUNTIME/source).rename(ROOT/target)
def translate(text):
 for old,new in mapping.items():text=text.replace(old,new)
 return text
provenance={}
scripts=[]
for d in [ROOT/'agents',ROOT/'lingo_sol',ROOT/'molclaw']:
 scripts.extend(p for p in d.rglob('*') if p.is_file() and p.suffix in ('.py','.ts','.json') and 'node_modules' not in p.parts)
for name in ['chatdrug_generalization_20260920','agentdrug_20260922','molingo_20260922','molclaw_20260924']:
 scripts.extend((RUNTIME/name).glob('*.py'))
scripts.extend((RUNTIME/'.local/share/sol-pi-deps').rglob('*.py'))
for p in scripts:
 provenance[str(p.relative_to(ROOT))]=sha(p)
 text=translate(p.read_text())
 if p.is_relative_to(ROOT/'agents') or p.is_relative_to(ROOT/'lingo_sol') or p.is_relative_to(ROOT/'molclaw'):
  text=text.replace('gpt-6-luna',MODEL).replace('mol-edit-gpt6luna','mol-edit-glm53flash')
  text=text.replace("'reasoning_effort':'none'","'reasoning_effort':'low'").replace("reasoning_effort='none'","reasoning_effort='low'")
  text=text.replace("['reasoning_effort']=='none'","['reasoning_effort']=='low'")
  text=text.replace("get('reasoning_effort')=='none'","get('reasoning_effort')=='low'")
 p.write_text(text)
for dirname in ['chatdrug_generalization_20260920/venv','molclaw_20260924/isolated_env']:
 env=RUNTIME/dirname
 for p in (env/'bin').iterdir():
  if p.is_symlink() and p.name.startswith('python'):p.unlink();p.symlink_to(CPU_PY)
  elif p.is_file():
   try:
    text=p.read_text()
    if text.startswith('#!'):p.write_text(translate(text))
   except UnicodeDecodeError:pass
 cfg=(env/'pyvenv.cfg').read_text();cfg=re.sub(r'^home = .*', 'home = '+str(CPU_PY.parent),cfg,flags=re.M)
 (env/'pyvenv.cfg').write_text(cfg)
provider=ROOT/'agents/provider.py'
text=provider.read_text();tree=ast.parse(text);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='config')
lines=text.splitlines(True)
lines[node.lineno-1:node.end_lineno]=["def config():\n    return {'base':'http://127.0.0.1:18853/v4','key':'local-glm-boundary'}\n"]
text=''.join(lines).replace("'tok.fan'","'open.bigmodel.cn via isolated local gateway'")
provider.write_text(text);(ROOT/'lingo_sol/provider.py').write_text(text)
for d in [ROOT/'agents',ROOT/'lingo_sol',ROOT/'molclaw']:
 (d/'private').mkdir(mode=0o700,exist_ok=True)
 (d/'private/chatgpt.env').write_text('BASE_URL=http://127.0.0.1:18853/v4\nAPI_KEY=local-glm-boundary\n')
 os.chmod(d/'private/chatgpt.env',0o600)
workers={'agents':16,'lingo_sol':8,'molclaw':8}
for d,n in workers.items():
 p=ROOT/d/'run.py';text=p.read_text();text=re.sub(r'WORKERS=\d+',f'WORKERS={n}',text);p.write_text(text)
p=ROOT/'lingo_sol/sol_pi/run.py';text=p.read_text()
text=text.replace('HOME = Path.home()',f'HOME = Path({str(RUNTIME)!r})')
text=text.replace("cmd = ['bwrap',",f"cmd = [{str(ROOT/'bin/bwrap')!r},")
text=text.replace("paths += [MOL / 'isolated_env'",f"paths += [Path({str(ROOT/'node')!r}), Path({str(CPU_PY.parent.parent)!r}), MOL / 'isolated_env'")
text=text.replace("cmd += ['--ro-bind', str(path), str(path)]",f"cmd += ['--ro-bind', str(path), '/opt/codex-node' if path == Path({str(ROOT/'node')!r}) else str(path)]")
text=text.replace("'--ro-bind', '/usr/bin/python3.10'",f"'--ro-bind', {str(CPU_PY)!r}")
text=text.replace("'--thinking', 'off'","'--thinking', 'low'")
p.write_text(text)
p=ROOT/'molclaw/claw_agent.py';text=p.read_text()
text=text.replace("env['PATH']=str(ROOT/'isolated_env/bin')+os.pathsep+env.get('PATH','')",f"env['PATH']={str(ROOT/'node/bin')!r}+os.pathsep+str(ROOT/'isolated_env/bin')+os.pathsep+env.get('PATH','')")
p.write_text(text)
proxy='''import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CLAW=Path(RUNTIME_PATH)
port=json.loads((ROOT/'proxy_port.json').read_text())['port']
os.environ['MOLCLAW_GPT_API_KEY']='local-glm-boundary'
cfg={'model_list':[{'model_name':'*','litellm_params':{'model':'openai/glm-5.3-flash','api_base':'http://127.0.0.1:18853/v4','api_key':'os.environ/MOLCLAW_GPT_API_KEY','extra_body':{'reasoning_effort':'low'}}}], 'litellm_settings':{'drop_params':True,'set_verbose':False,'callbacks':['audit_callback.audit_logger']},'general_settings':{'disable_spend_logs':True}}
config=ROOT/'proxy_config.yaml';config.write_text(json.dumps(cfg));os.chmod(config,0o600)
os.environ['PYTHONPATH']=str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')
os.chdir(ROOT)
os.execv(str(CLAW/'isolated_env/bin/litellm'),['litellm','--config',str(config),'--host','127.0.0.1','--port',str(port)])
'''.replace('RUNTIME_PATH',repr(str(RUNTIME/'molclaw_20260924')))
(ROOT/'molclaw/launch_proxy.py').write_text(proxy)
os.chmod(RUNTIME/'molclaw_20260924/private/scp.env',0o600)
for d in ['agents','lingo_sol','molclaw']:
 path=ROOT/d/'manifest.json';manifest=json.loads(path.read_text())
 manifest['source_manifest']=dict(manifest)
 manifest['model']=MODEL;manifest['reasoning_effort']='low';manifest['provider']='Official BigModel API via shared adaptive loopback gateway'
 manifest['workers']=workers[d];manifest['cpu_host']='159.138.92.174';manifest['migration']='Only runtime paths, model/provider and concurrency changed; native parsers, budgets, cases and evaluation retained.'
 manifest['frozen_dependencies']={translate(name):sha(Path(translate(name))) for name in manifest['frozen_dependencies']}
 for name,file in [('common_sha256','common.py'),('native_chat_sha256','chat_native.py'),('jobs_sha256','jobs.json')]:
  if name in manifest:manifest[name]=sha(ROOT/d/file)
 manifest['code_hashes']={str(p.relative_to(ROOT/d)):sha(p) for p in (ROOT/d).rglob('*.py')}
 path.write_text(json.dumps(manifest,indent=2))
 jobs=json.loads((ROOT/d/'jobs.json').read_text())
 assert len(jobs)==4200
 if d=='agents':frozen=jobs
 else:assert jobs==frozen
 assert collections.Counter(j['setting'] for j in jobs)=={'1_original_chatdrug':1600,'2_s2_prompt_chatdrug':1600,'3_original_s2':1000}
for p in [*(ROOT/'agents').glob('*.py'),*(ROOT/'lingo_sol').rglob('*.py'),*(ROOT/'molclaw').glob('*.py')]:ast.parse(p.read_text())
(ROOT/'source_provenance.json').write_text(json.dumps(provenance,indent=2))
(ROOT/'prepared.json').write_text(json.dumps({'prepared':True,'model':MODEL,'methods':['ChatDrug','AgentDrug','MolLingo(single)','MolClaw(both)','SoL-Pi(all four)'],'total':21000,'workers':{'ChatDrug+AgentDrug':16,'MolLingo':8,'SoL-Pi':8,'MolClaw':8},'shared_api_limit':32,'final_scoring':'Official S2 descriptors, strict direction only, no amplitude, no similarity threshold; one final submission'},indent=2))
print('CPU_PREPARED_21000_CASES',flush=True)
