import importlib.util,json,sys,time
from pathlib import Path
r=Path(__file__).resolve().parent;root=r/'codex'
spec=importlib.util.spec_from_file_location('codex_relay_check',root/'run_benchmark.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.validate()
ident='relay_smoke_'+str(int(time.time()))
c=dict(module.JOBS[0]['case'],id=ident,bench='ChatDrug',bucket='probe',index=0)
row=module.native.execute(c,'relay_preflight',prompt_override='Use your shell tool to run Python, import rdkit, compute 17*19, and write the result to probe.txt. Read it back with a shell tool. Finish saying SMOKE_OK. Work only in /workspace.')
assert row['status']=='complete' and row.get('tool_calls',0)>=1,row.get('error')
assert (root/'native/work/relay_preflight'/ident/'probe.txt').read_text().strip()=='323'
aa=[json.loads(p.read_text()) for p in (root/'native/runs/relay_preflight'/ident/'api').glob('*.json')]
real=[a for a in aa if a.get('response')]
assert len(real)>=2 and all(a['response']['model']=='glm-5.3-flash' for a in real)
report={'passed':True,'id':ident,'native_tool_calls':row['tool_calls'],'real_glm_responses':len(real),
 'provider':'https://tok.fan/v1','model':'glm-5.3-flash','time':time.time()}
(root/'relay_native_smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
