from pathlib import Path
import json,subprocess,os,time,sys
import run
from runtime import ROOT,Executor,dump
from agent_harness.config import AgentConfig
tid=json.loads((ROOT/'public_tasks.json').read_text())[0]['id'];test=ROOT/'preflight/models';run.prepare(test)
cmd=run.command(test,9,True)
proc=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
dump(ROOT/'preflight/model_list.json',{'exit':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
assert proc.returncode==0 and run.MODEL in proc.stdout,proc.stderr
prefix=cmd[:cmd.index('/opt/codex-node/bin/node')]
list_cmd=prefix+['/opt/codex-node/bin/node','/opt/sol-pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js','list','--approve']
listed=subprocess.run(list_cmd,capture_output=True,text=True,timeout=60)
dump(ROOT/'preflight/packages.json',{'exit':listed.returncode,'stdout':listed.stdout,'stderr':listed.stderr});assert listed.returncode==0 and '/opt/sol-pi' in listed.stdout,listed.stderr
env=dict(os.environ,OPENSSL_CONF='/dev/null',PATH='/opt/codex-node/bin:'+os.environ.get('PATH',''))
cfg=subprocess.run([str(ROOT/'node/bin/node'),str(run.SOL/'scripts/check-sol-pi-config.mjs'),'--config',str(test/'.agent/sol-pi.json'),'--require-all-enabled'],capture_output=True,text=True,env=env)
dump(ROOT/'preflight/config_validation.json',{'exit':cfg.returncode,'stdout':cfg.stdout,'stderr':cfg.stderr});assert cfg.returncode==0,cfg.stderr
for hidden in ['/data/chenfuxin/a100_migration_20261016/workspace/yimin/zlc/molclaw_type4_20261003/runs','/data/chenfuxin/a100_migration_20261016/workspace/yimin/zlc/molclaw_type4_20261003/private','/eval/code']:
 assert subprocess.run(prefix+['/usr/bin/test','!','-e',hidden]).returncode==0
print('MODEL_PACKAGE_FLAGS_AND_ISOLATION_PASSED',flush=True)
result=run.job(tid,True);assert result['status']=='complete',result
out=ROOT/'preflight/solpi'/tid;proof=json.loads((out/'workspace/.pi/loaded-runtime.json').read_text())
names={t['name']:t['parameters'] for t in proof['tools']}
assert all(k in names for k in ['python','predict_admet','predict_boltz','submit','obs_recall','update_plan'])
assert 'then_run' in names['write']['properties'] and 'then_run' in names['edit']['properties']
requests=[]
for p in out.glob('api/*.json'):
 d=json.loads(p.read_text());body=d['request'];assert body['enable_thinking'] is False and body['temperature']==1 and 'reasoning_effort' not in body
 assert d['response']['model']=='deepseek-v4.1-flash';requests.append(str(p.relative_to(ROOT)))
assert requests
exec=Executor(str(test),AgentConfig(admet_budget=0,boltz_budget=0))
for name in ['predict_admet','predict_boltz']:assert exec.dispatch(name,{})[1].get('budget_exceeded')
assert run.guard('write',{'path':'.agent/sol-pi.json','content':'{}'})
assert run.guard('write',{'path':'test.txt','content':'a','then_run':{'command':'curl http://x'}})
assert not run.guard('write',{'path':'test.txt','content':'a','then_run':{'command':'wc -c test.txt'}})
dump(ROOT/'preflight/result.json',{'passed':True,'model':run.MODEL,'enable_thinking':False,'temperature':1,'all_four_mechanisms':True,'provider_requests_checked':requests,'official_oracle_budget_guards':True,'runtime_tool_schemas':proof,'time':time.time()})
print('ALL_SOL_PI_PREFLIGHT_PASSED',flush=True)
