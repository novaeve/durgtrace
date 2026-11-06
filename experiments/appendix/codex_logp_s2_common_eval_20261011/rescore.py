"""Offline official S2 LogP scoring of saved native Codex final outputs."""
from pathlib import Path
import ast,collections,functools,hashlib,json,sys,time,os
import rdkit
from rdkit import Chem,RDLogger
from rdkit.Chem import Descriptors
ROOT=Path(__file__).resolve().parent
BASE=Path('/data/chenfuxin/codex_chatdrug_molopt_loopguard_c16_resume2_20261011')
SOURCE=Path('/data2/chenfuxin/chatdrug_generalization_20260920/upstream/S2-TOMG-Bench/utils/evaluation.py')
REFERENCE=Path('/data2/chenfuxin/molopt_original_bailian_20261007/s2_common_task_evaluation/summary.json')
NOAMP=Path('/data/chenfuxin/codex_chatdrug_amplitude_ablation_20261011/rows.json')
sys.path.insert(0,str(BASE))
import score

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):
 tmp=p.with_suffix('.tmp')
 with tmp.open('w') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 tmp.replace(p)
def main():
 assert not (ROOT/'summary.json').exists(),'Existing evaluation is preserved'
 ref=json.loads(REFERENCE.read_text());assert sha(SOURCE)==ref['s2_property_code_sha256'];assert rdkit.__version__==ref['rdkit_version']=='2022.09.4'
 node=next(n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='mol_prop');ns={'Chem':Chem,'Descriptors':Descriptors};exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),ns);mol_prop=functools.lru_cache(maxsize=30000)(ns['mol_prop'])
 RDLogger.DisableLog('rdApp.*');evaluate,_=score.original_evaluator()
 combined_path=BASE/'combined_latest_7100.json';combined_hash=sha(combined_path);combined=json.loads(combined_path.read_text());assert combined['phase']=='complete';source_rows={x['id']:x for x in combined['rows']}
 cases=[c for c in json.loads((BASE/'original_cases.json').read_text()) if c['property']=='LogP' and len(c['objectives'])==1];assert len(cases)==len({c['id'] for c in cases})==1300
 noamp_hash=sha(NOAMP);noamp={x['id']:x for x in json.loads(NOAMP.read_text())};groups=collections.defaultdict(collections.Counter);details=[];hashes={};evaluation_hashes={}
 for case in cases:
  stored=source_rows[case['id']];path=Path(stored['result_path']);epath=Path(stored['evaluation_path']);hashes[str(path)]=sha(path);evaluation_hashes[str(epath)]=sha(epath);generation=json.loads(path.read_text());e=json.loads(epath.read_text());assert e['protocol']=='original' and e['evaluation_calls']==1
  assert generation['id']==case['id'] and generation['status']==stored['result']['status'];complete=generation['status']=='complete';candidate=generation.get('candidate') if complete else None
  original=evaluate(case,candidate);assert original==stored['score']==e['score'],case['id'];direction=case['objectives'][0][1]
  if case['benchmark']=='ChatDrug':assert direction=={101:-1,102:1}[case['task']]
  else:
   lower=any(w in case['instruction'].lower() for w in ('lower','decrease'));assert direction==(-1 if lower else 1)
  valid=bool(complete and isinstance(candidate,str) and mol_prop(candidate,'validity'));before=mol_prop(case['smiles'],'logP');after=mol_prop(candidate,'logP') if valid else None;assert before is not None
  success=bool(valid and (after<before if direction==-1 else after>before));saved=bool(original['success'])
  if case['benchmark']=='S2-mini':assert success==saved,case['id']
  zero_success=bool(noamp[case['id']]['direction_only_score']['success']) if case['benchmark']=='ChatDrug' else saved
  labels=[case['benchmark'],case['benchmark']+'_'+('higher' if direction==1 else 'lower')]
  if case['benchmark']=='ChatDrug':labels.extend(['task_'+str(case['task']),case['benchmark']+'_'+case['constraint']])
  for label in labels:
   g=groups[label];g['expected']+=1;g['complete']+=complete;g['valid']+=valid;g['original_success']+=saved;g['no_amplitude_kekule_success']+=zero_success;g['s2_success']+=success;g['rescued_vs_original']+=success and not saved;g['lost_vs_original']+=saved and not success;g['rescued_vs_noamplitude']+=success and not zero_success;g['lost_vs_noamplitude']+=zero_success and not success
  details.append({'id':case['id'],'benchmark':case['benchmark'],'property':'LogP','original_setting':case['constraint'],'status':generation['status'],'source':str(path),'candidate':candidate,'direction':direction,'valid':valid,'original_success':saved,'no_amplitude_kekule_success':zero_success,'s2_success':success,'s2_input_logp':before,'s2_output_logp':after,'chatdrug_kekule_input_logp':original.get('input_property'),'chatdrug_kekule_output_logp':original.get('output_property'),'harness_variant':stored['harness_variant']})
 output={}
 for label,counts in groups.items():
  g=dict(counts);g.update(original_rate=g['original_success']/g['expected'],no_amplitude_kekule_rate=g['no_amplitude_kekule_success']/g['expected'],s2_rate=g['s2_success']/g['expected']);output[label]=g
 assert output['ChatDrug']['expected']==800 and output['S2-mini']['expected']==500
 assert output['ChatDrug']['original_success']==744 and output['ChatDrug']['no_amplitude_kekule_success']==781
 assert output['S2-mini']['s2_success']==471
 assert sha(combined_path)==combined_hash and sha(NOAMP)==noamp_hash
 assert all(sha(Path(p))==digest for p,digest in hashes.items()) and all(sha(Path(p))==digest for p,digest in evaluation_hashes.items())
 report={'method':'codex','model':'deepseek-v4.1-flash','protocol':ref['protocol'],'direction_mapping':ref['direction_mapping'],'input_combined':str(combined_path),'input_combined_sha256':combined_hash,'case_sha256':sha(BASE/'original_cases.json'),'rdkit_version':rdkit.__version__,'s2_property_code_sha256':sha(SOURCE),'reference_summary':str(REFERENCE),'reference_script_sha256':sha(REFERENCE.parent.parent/'rescore_s2_common_tasks.py'),'script_sha256':sha(Path(__file__)),'source_result_sha256':hashes,'source_evaluation_sha256':evaluation_hashes,'no_amplitude_rows_sha256':noamp_hash,'api_calls':0,'groups':output,'validation':{'original_scores_reproduced':1300,'S2_LogP_500_outcomes_unchanged':True,'same_800_chatdrug_final_candidates':True,'input_results_and_scores_unchanged':True},'limits':ref['limits'],'time':time.time()}
 dump(ROOT/'rows.json',details);dump(ROOT/'summary.json',report)
 print(json.dumps({'groups':output,'api_calls':0,'rdkit':rdkit.__version__,'output':str(ROOT)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
