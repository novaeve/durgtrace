import importlib.util,json,tempfile
from pathlib import Path
base=Path(__file__).resolve().parent
for name in ('parallel_codex_recovery','resilience_common'):
 s=importlib.util.spec_from_file_location(name,base/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);globals()[name]=m
old={'status':'error','retryable':True,'infrastructure_recovery_reason':'verified network fault','case':{'id':'x'},'candidate':None,'score':{'success':False}}
claim={'token':'t','pid':1};claimed=parallel_codex_recovery.claim_row(old,claim)
assert claimed['retryable'] is False and claimed['score']==old['score']
assert resilience_common.recoverable(claimed)
new={'status':'complete','case':{'id':'x'},'candidate':'CCO','score':{'success':False},'setting':'parallel'}
assert parallel_codex_recovery.promoted_row(new,'original')['score']==new['score']
try:parallel_codex_recovery.claim_row(dict(old,status='timeout'),claim)
except AssertionError:pass
else:raise AssertionError('Scientific timeout was claimed')
with tempfile.TemporaryDirectory() as tmp:
 r=Path(tmp);method=r/'codex';method.mkdir();job={'setting':'original','case':{'id':'x'}};(method/'jobs.json').write_text(json.dumps([job]));final=method/'runs/Codex/original/x';final.mkdir(parents=True)
 cache=method/'parallel/cache.json';cache.parent.mkdir();cache.write_text(json.dumps(new));claimed['infrastructure_parallel_claim']['scratch_final']=str(cache);claimed['infrastructure_parallel_claim']['native_result']=str(method/'native/runs/parallel/x/result.json');(final/'result.json').write_text(json.dumps(claimed))
 repaired=resilience_common.repair_idle_codex(r);restored=json.loads((final/'result.json').read_text());assert repaired and restored['candidate']=='CCO' and restored['score']==new['score'] and restored['setting']=='original';assert 'infrastructure_parallel_claim' not in restored
print('PARALLEL_CLAIM_FENCE_AND_CACHED_RESULT_RECOVERY_PASSED')
