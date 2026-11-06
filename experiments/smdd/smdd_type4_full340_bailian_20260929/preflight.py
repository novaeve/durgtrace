import hashlib,json,pathlib,subprocess,sys,yaml
R=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(R/'harness'))
from agent_harness.config import AgentConfig
from agent_harness.obfuscate import obfuscate_task,cleanup_obfuscated
from transport_adapter import request,complete
from agentdrug_smdd import AgentDrugExecutor
from batch import TASKS
ids=(R/'tasks340.txt').read_text().splitlines();assert len(ids)==340
for tid in ids:
 t=yaml.safe_load((TASKS/tid/'task.yaml').read_text())
 assert 'description' in t and (TASKS/tid/'protein.fasta').exists()
 assert all(x in t['description'] for x in ('Tanimoto','0.7'))
tmp=obfuscate_task(str(TASKS/ids[0]),'task_000')
try:
 files=[p.name for p in pathlib.Path(tmp).iterdir()];assert not any('witness' in n for n in files)
 out=R/'preflight';out.mkdir(exist_ok=True)
 e=AgentDrugExecutor('not-used',AgentConfig(),yaml.safe_load((TASKS/ids[0]/'task.yaml').read_text()),tmp,str(out))
 assert e.proteins and e.contacts and all(p['id'] in [x['id'] for x in e.proteins] for p in e.proteins)
 assert set(c[0] for c in e.contacts).issubset({p['id'] for p in e.proteins})
 assert e.assess('invalid_SMILES')[0] is False and e.admet_calls==0
 e.admet_calls=15;e.boltz_calls=8
 assert e.admet('CC') is None and e.bind('CC') is None
finally:cleanup_obfuscated(tmp)
resp=request([{'role':'user','content':'Reply exactly OK.'}],max_tokens=32)
assert resp['choices'][0]['message']['content'].strip()=='OK',resp
adapted=complete('ignored',[{'role':'user','content':'Reply exactly OK.'}],None,0)
assert adapted.output and adapted.usage
manifest={'model':'deepseek-v4.1-flash','provider':'Alibaba Bailian','tasks':340,'task_manifest_sha256':hashlib.sha256((R/'tasks340.txt').read_bytes()).hexdigest(),'key_location':'original GPU server only; SSH relay returns responses','budget_per_task':{'admet':15,'boltz':8,'total_tokens':10000000,'harness_turns':100},'chatdrug':{'source':'existing SMDD ChatDrug ReDF adapter, with native generated-molecule similarity ranking','fingerprint':'Morgan radius 2 count fingerprint, Tanimoto descending','retrieval_similarity_cutoff':None,'refinement_rounds':2,'temperature':1,'stop_on_no_reference':True},'agentdrug':{'source':'existing AgentDrug core_fixed.py; new documented SMDD oracle adapter','max_generations':5,'max_output_tokens':256,'temperature':0,'continue_on_no_reference':True,'last_generation_is_final':True,'retrieval_similarity_cutoff':None},'retrieval':'same fixed 10000 molecule corpus, exact task input excluded; all learned oracle lookups charged to task budget','evaluation':'original smdd-evals:359ef1d7; retains final Tanimoto >=0.7; GPU bridge only','continuation':'scientific failure or budget exhaustion never stops batch; infrastructure errors recorded separately; denominator340 each','code_hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'batch.py',R/'agentdrug_smdd.py',R/'agentdrug_core_source.py',R/'chatdrug_adapter.py',R/'frozen_lead_optimization.py',R/'transport_adapter.py',R/'gpu_transport.py',R/'retrieval.csv']},'checks':{'tasks':len(ids),'public_files_only':files,'provider_response_model':resp.get('model'),'adapter_success':True,'budget_guard_success':True,'invalid_smiles_no_oracle_calls':True}}
(R/'protocol_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
