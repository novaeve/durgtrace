"""Offline adapter tests: stage-specific repeated IDs and secret-free model receipts."""
import ast,importlib.util,json,pathlib,sys,tempfile,types
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent
import audit_callback as audit
jobs=json.loads((ROOT/'jobs.json').read_text())
source=ast.parse((ROOT/'claw_agent.py').read_text())
nodes=[n for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('ROOT','EXP','cases','case') for t in n.targets)]
code=compile(ast.Module(body=nodes,type_ignores=[]),'isolated_case_lookup','exec')
for setting in ('1_original_chatdrug','2_s2_prompt_chatdrug','3_original_s2'):
 chosen=next(j['case'] for j in jobs if j['setting']==setting)
 ns={'pathlib':pathlib,'json':json,'sys':types.SimpleNamespace(argv=['claw_agent.py',setting,chosen['id']]),'__file__':str(ROOT/'claw_agent.py')}
 exec(code,ns)
 assert ns['case']==chosen
case='1_original_chatdrug/source_101_loose_000'
assert audit.case_label({'headers':{'X-MolClaw-Case':case}})==case
assert audit.case_label({'headers':{'X-MolClaw-Case':'../../private'}}) is None
with tempfile.TemporaryDirectory(dir=ROOT) as folder,patch.object(audit,'ROOT',pathlib.Path(folder)):
 sentinel='TEST_SECRET_MUST_NOT_BE_LOGGED'
 kwargs={'model':'glm-5.3-flash','litellm_params':{'api_key':sentinel,'extra_body':{'reasoning_effort':'low'},'metadata':{'headers':{'x-molclaw-case':case,'authorization':sentinel}}}}
 response={'model':'glm-5.3-flash','choices':[{'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':5}}
 audit.save(kwargs,response,'complete')
 files=list(pathlib.Path(folder).rglob('*.json'));assert len(files)==1
 text=files[0].read_text();assert sentinel not in text
 receipt=json.loads(text);assert receipt['response_model_ok'] and receipt['case']==case
 assert receipt['extra_reasoning_effort']=='none'
 kwargs['exception']=RuntimeError(sentinel);audit.save(kwargs,{},'error')
 assert all(sentinel not in f.read_text() for f in pathlib.Path(folder).rglob('*.json'))
print('STAGE_LOOKUP_AND_PROVIDER_AUDIT_CHECK_PASSED',flush=True)
