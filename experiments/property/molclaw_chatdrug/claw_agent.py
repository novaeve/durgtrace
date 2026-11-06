import os,pathlib,json,shutil,subprocess,time,ast,sys
ROOT=pathlib.Path('/data/chenfuxin/a100_migration_20261016/workspace/home/zlc/molclaw_chatdrug_aligned_20261012/bundle')
EXP=pathlib.Path('/data/chenfuxin/a100_migration_20261016/workspace/home/zlc/molclaw_chatdrug_aligned_20261012')
UP=ROOT/'source/MolClaw-main'
cases=json.loads((EXP/'cases.json').read_text())
case=next(c for c in cases if c['id']==sys.argv[2]) if len(sys.argv)>2 else next(c for c in cases if c['benchmark']=='ChatDrug')
stage=sys.argv[1] if len(sys.argv)>1 else 'smoke'
out=EXP/'native/MolClaw'/stage/case['id'];out.mkdir(parents=True,exist_ok=True)
shutil.copytree(UP/'skills',out/'.claude/skills',dirs_exist_ok=True)
mcp={'mcpServers':{'molclaw-scp':{'type':'http','url':'https://scp.intern-ai.org.cn/api/v1/mcp/2/DrugSDA-Tool','headers':{'SCP-HUB-API-KEY':'${SCP_HUB_API_KEY}'}}}}
(out/'.mcp.json').write_text(json.dumps(mcp))
env=dict(os.environ)
env.pop('ANTHROPIC_API_KEY',None)
env['PATH']=str(ROOT/'isolated_env/bin')+os.pathsep+env.get('PATH','')
env['VIRTUAL_ENV']=str(ROOT/'isolated_env')
env.update(ANTHROPIC_BASE_URL='http://127.0.0.1:49493',ANTHROPIC_AUTH_TOKEN='local-molclaw-proxy',ANTHROPIC_MODEL='deepseek-v4.1-flash',ANTHROPIC_DEFAULT_HAIKU_MODEL='deepseek-v4.1-flash',ANTHROPIC_DEFAULT_SONNET_MODEL='deepseek-v4.1-flash',ANTHROPIC_DEFAULT_OPUS_MODEL='deepseek-v4.1-flash',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',MAX_THINKING_TOKENS='0')
env['SCP_HUB_API_KEY']=(ROOT/'private/scp.env').read_text().strip().split('=',1)[1]
env['CLAUDE_CONFIG_DIR']=str(out/'.runtime')
# Use the author's prompt builder without importing unrelated benchmark packages.
tree=ast.parse((UP/'molclaw_run/infer/claude_agent/run_claude.py').read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_build_prompt')
ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'upstream_prompt','exec'),ns)
prompt=ns['_build_prompt'](case['instruction'],'Submit exactly ONE final molecule as a SMILES string inside <answer>...</answer>. Do not put a list or multiple alternatives in the answer tag.','both',None)
(out/'prompt.txt').write_text(prompt)
metadata=EXP/'case_manifests'/stage;metadata.mkdir(parents=True,exist_ok=True)
(metadata/(case['id']+'.json')).write_text(json.dumps(case))
cmd=[str(ROOT/'runtime/node_modules/.bin/claude'),'--dangerously-skip-permissions','-p','--model','deepseek-v4.1-flash','--output-format','stream-json','--verbose','--mcp-config',str(out/'.mcp.json'),'--strict-mcp-config']
cmd=['unshare','--user','--map-current-user','--pid','--fork','--mount-proc','--']+cmd
start=time.time()
with (out/'events.jsonl').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
 p=subprocess.run(cmd,input=prompt,text=True,cwd=out,env=env,stdout=stdout,stderr=stderr)
(out/'exit.json').write_text(json.dumps({'returncode':p.returncode,'seconds':time.time()-start}))
print(json.dumps({'id':case['id'],'returncode':p.returncode,'seconds':time.time()-start}),flush=True)
raise SystemExit(p.returncode)
