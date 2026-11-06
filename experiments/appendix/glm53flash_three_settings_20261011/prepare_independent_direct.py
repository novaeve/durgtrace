"""Exclude the paired arm and create a clean independent baseline directory."""
import collections,hashlib,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
assert ROOT==Path('/data/chenfuxin/glm53flash_three_settings_20261011')
DIRECT=ROOT/'direct'
if DIRECT.exists() and json.loads((DIRECT/'manifest.json').read_text()).get('generation')!='independent_single_response_no_harness':
    archive=ROOT/'excluded_results'/('paired_chatdrug_direct_'+str(int(time.time())))
    archive.parent.mkdir(exist_ok=True)
    DIRECT.rename(archive)
    (archive/'EXCLUDED_FROM_FORMAL_COMPARISON.json').write_text(json.dumps({
        'reason':'User requires fresh independent model calls with no harness; paired ChatDrug responses are excluded',
        'excluded':True,'time':time.time()},indent=2))
    print('EXCLUDED_ARCHIVE '+str(archive),flush=True)
DIRECT.mkdir(exist_ok=True)
for name in ('jobs.json','common.py'):
    if not (DIRECT/name).exists():shutil.copy2(ROOT/'agents'/name,DIRECT/name)
shutil.copy2(ROOT/'direct_independent.py',DIRECT/'run.py')
jobs=json.loads((DIRECT/'jobs.json').read_text());assert len(jobs)==4200
assert len({(j['setting'],j['case']['id']) for j in jobs})==4200
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('independent_run',DIRECT/'run.py');module=module_from_spec(spec);spec.loader.exec_module(module)
for job in jobs:
    body=module.request_body(job['case'])
    assert len(body['messages'])==1 and body['n']==1 and 'tools' not in body
    assert body['messages'][0]['content'].startswith(job['case']['instruction'])
    assert module.score(job['case'],job['case']['smiles'])['success'] is False
assert module.parse_single('CCO\nCCN') is None
assert module.parse_single('```CCO```') is None
manifest={'model':module.MODEL,'generation':'independent_single_response_no_harness',
    'created':time.time(),'expected':4200,'workers':module.WORKERS,
    'jobs_sha256':hashlib.sha256((DIRECT/'jobs.json').read_bytes()).hexdigest(),
    'runner_sha256':hashlib.sha256((DIRECT/'run.py').read_bytes()).hexdigest(),
    'official_upstream':'https://open.bigmodel.cn/api/paas/v4/chat/completions',
    'transport':'CPU localhost credential/concurrency gateway; messages unchanged',
    'request':{'temperature':0,'reasoning_effort':'low','max_tokens':2048,'n':1},
    'prompt':'Original case instruction plus a single-SMILES output-format instruction; no system message',
    'output_rule':module.OUTPUT_RULE,'tools':False,'history':False,'feedback':False,
    'candidate_selection':False,'response_reuse_from_other_methods':False,
    'parse':'Trim whole response only; reject multiple tokens, markdown fences or non-SMILES; no extraction or repair',
    'scientific_retry':False,'evaluation':'Official S2 strict directional score, no amplitude or similarity threshold'}
module.dump(DIRECT/'manifest.json',manifest)
module.dump(DIRECT/'independent_validation.json',{'cases_checked':4200,'same_jobs_as_agents':True,
    'self_submission_never_improves':True,'single_response_no_tools_no_history':True,'time':time.time()})
if not (DIRECT/'state.json').exists():module.dump(DIRECT/'state.json',{'phase':'ready','processed':0,'expected':4200,'workers':16})
expanded=ROOT/'expanded_experiment.json'
if expanded.exists():
    data=json.loads(expanded.read_text());data['direct_generation']='independent_single_response_no_harness'
    data['previous_paired_direct_excluded']=True;module.dump(expanded,data)
print(json.dumps({'independent_cases':4200,'groups':dict(collections.Counter(j['setting'] for j in jobs)),
    'workers':16,'processed':json.loads((DIRECT/'state.json').read_text()).get('processed')}),flush=True)
