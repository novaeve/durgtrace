from pathlib import Path
import json,subprocess,sys,hashlib
import runtime
from runtime import ROOT,dump,Executor
from agent_harness.config import AgentConfig
import run
ids=[t['id'] for t in json.loads((ROOT/'public_tasks.json').read_text())];assert len(ids)==340
task=ids[0];out=ROOT/'preflight/deepseek/tool_smoke';out.mkdir(parents=True,exist_ok=True)
description='Use the python tool to import rdkit, compute 17*19, and write 323 to probe.txt. Read it back using the python tool, then call submit with probe.txt. Do not solve the molecule task.'
status=runtime.baseline({'id':'tool_smoke','description':description},ROOT/'public_inputs'/task,out)
assert status['status']=='submitted',status
assert (out/'workspace/probe.txt').read_text().strip()=='323'
dump(out/'result.json',dict(status,passed=True))
print('BASELINE_LIVE_TOOL_SMOKE_PASSED',flush=True)
result=run.job('codex',task,0,True)
assert result['status']=='complete',result
print('CODEX_LIVE_MCP_TOOL_SMOKE_PASSED',flush=True)
for work in [out/'workspace',ROOT/'preflight/codex'/task/'workspace']:
 text,rc=runtime.isolated(['python','-c',"import os;assert not os.path.exists('/eval/code');assert not os.path.exists('/data2/chenfuxin');import rdkit;print('hidden_inputs_absent')"],work)
 assert rc==0,text
 print(text.strip(),flush=True)
executor=Executor(str(out/'workspace'),AgentConfig(admet_budget=0,boltz_budget=0))
for name in ['predict_admet','predict_boltz']:
 result,extra=executor.dispatch(name,{})
 assert extra.get('budget_exceeded') and 'budget exceeded' in result.lower()
print('OFFICIAL_ORACLE_BUDGETS_ENFORCED',flush=True)
assert not any(p.name=='task.yaml' for p in (ROOT/'public_inputs').glob('*/*'))
sourcehash={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'upstream/agent_harness').glob('*.py')}
dump(ROOT/'preflight/result.json',{'passed':True,'model':'deepseek-v4.1-flash','enable_thinking':False,'temperature':1,'official_harness_hashes':sourcehash,'codex_cli':subprocess.check_output([str(ROOT/'bin/codex'),'--version'],text=True).strip()})
print('ALL_PREFLIGHT_PASSED',flush=True)
