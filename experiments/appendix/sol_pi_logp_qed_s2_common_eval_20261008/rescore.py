"""Offline SoL-Pi LogP/QED scoring with the same official S2 protocol as other agents."""
from pathlib import Path
import ast,collections,functools,hashlib,json,sys,time
import rdkit
from rdkit import Chem,RDLogger
from rdkit.Chem import Descriptors
ROOT=Path(__file__).resolve().parent
BASE=Path('/data/chenfuxin/sol_pi_chatdrug_molopt_20261007')
CHAT=Path('/data2/chenfuxin/chatdrug_generalization_20260920')
REFERENCE=Path('/data2/chenfuxin/molopt_original_bailian_20261007/s2_common_task_evaluation/summary.json')
SCORER=Path('/data/chenfuxin/sol_pi_chatdrug_infra_rerun19_20261008')
sys.path.insert(0,str(SCORER))
import score
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not (ROOT/'summary.json').exists(),'Existing evaluation is preserved'
 ref=json.loads(REFERENCE.read_text())
 source=CHAT/'upstream/S2-TOMG-Bench/utils/evaluation.py'
 assert sha(source)==ref['s2_property_code_sha256']
 assert rdkit.__version__==ref['rdkit_version']=='2022.09.4'
 nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='mol_prop']
 assert len(nodes)==1
 namespace={'Chem':Chem,'Descriptors':Descriptors}
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),namespace)
 mol_prop=functools.lru_cache(maxsize=30000)(namespace['mol_prop'])
 RDLogger.DisableLog('rdApp.*')
 evaluate,_=score.original_evaluator()
 link=json.loads((BASE/'audit_infra_20261008/rerun_reference.json').read_text())
 combined_path=Path(link['combined'])
 combined_hash=sha(combined_path)
 combined=json.loads(combined_path.read_text())
 source_rows={r['id']:r for r in combined['rows']}
 cases=[c for c in json.loads((BASE/'original_cases.json').read_text())
        if c['property'] in ('LogP','QED') and len(c['objectives'])==1]
 assert len(cases)==2600 and len({c['id'] for c in cases})==2600
 noamp={r['id']:r for r in json.loads(Path('/data/chenfuxin/sol_pi_chatdrug_amplitude_ablation_20261008/rows.json').read_text())}
 groups=collections.defaultdict(collections.Counter)
 details=[]
 hashes={}
 for case in cases:
  stored=source_rows[case['id']]
  path=Path(stored['source'])/'result.json'
  hashes[str(path)]=sha(path)
  generation=json.loads(path.read_text())
  assert generation['id']==case['id'] and generation['status']==stored['status']
  complete=generation['status']=='complete'
  candidate=generation.get('candidate') if complete else None
  original=evaluate(case,candidate)
  assert original['valid']==stored['score']['valid'] and original['success']==stored['score']['success'],case['id']
  prop=case['property'];direction=case['objectives'][0][1]
  if case['benchmark']=='ChatDrug':assert direction=={101:-1,102:1,103:1,104:-1}[case['task']]
  else:
   lower='lower' in case['instruction'] or 'decrease' in case['instruction']
   assert direction==(-1 if lower else 1)
  descriptor='logP' if prop=='LogP' else 'qed'
  valid=bool(complete and isinstance(candidate,str) and mol_prop(candidate,'validity'))
  before=mol_prop(case['smiles'],descriptor)
  after=mol_prop(candidate,descriptor) if valid else None
  assert before is not None
  success=bool(valid and (after-before)*direction>0)
  saved=bool(original['success'])
  if case['benchmark']=='S2-mini':assert success==saved,case['id']
  zero_success=noamp[case['id']]['direction_only_score']['success'] if case['benchmark']=='ChatDrug' else saved
  if prop=='QED':assert success==zero_success,case['id']
  labels=[case['benchmark'],case['benchmark']+'_'+case['direction']]
  if case['benchmark']=='ChatDrug':labels.append('ChatDrug_'+case['constraint'])
  for label in labels:
   g=groups[(label,prop)];g['expected']+=1;g['complete']+=complete;g['valid']+=valid
   g['original_success']+=saved;g['no_amplitude_kekule_success']+=zero_success;g['s2_success']+=success
   g['rescued_vs_original']+=success and not saved;g['lost_vs_original']+=saved and not success
   g['rescued_vs_noamplitude']+=success and not zero_success;g['lost_vs_noamplitude']+=zero_success and not success
  details.append({'id':case['id'],'benchmark':case['benchmark'],'property':prop,
                  'original_setting':case['constraint'],'status':generation['status'],'source':str(path),
                  'candidate':candidate,'direction':direction,'valid':valid,
                  'original_success':saved,'no_amplitude_kekule_success':zero_success,
                  's2_success':success,'input_property':before,'output_property':after})
 output=[]
 for (label,prop),counts in sorted(groups.items()):
  g=dict(counts)
  g.update(group=label,property=prop,original_rate=g['original_success']/g['expected'],
           s2_rate=g['s2_success']/g['expected'])
  if label in ('ChatDrug','S2-mini'):assert g['expected']==(800 if label=='ChatDrug' else 500)
  output.append(g)
 assert sha(combined_path)==combined_hash
 assert all(sha(Path(file))==digest for file,digest in hashes.items())
 report={'method':'SoL-Pi','protocol':ref['protocol'],'direction_mapping':ref['direction_mapping'],
         'input_combined':str(combined_path),'input_combined_sha256':combined_hash,
         'case_sha256':sha(BASE/'original_cases.json'),'rdkit_version':rdkit.__version__,
         's2_property_code_sha256':sha(source),'reference_summary':str(REFERENCE),
         'reference_script_sha256':sha(REFERENCE.parent.parent/'rescore_s2_common_tasks.py'),
         'script_sha256':sha(Path(__file__)),'source_result_sha256':hashes,'api_calls':0,
         'groups':output,'validation':{'original_scores_reproduced':2600,
          'S2_outcomes_unchanged':True,'ChatDrug_QED_same_as_direction_only':True,'input_results_unchanged':True},
         'limits':ref['limits'],'time':time.time()}
 (ROOT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 (ROOT/'rows.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
 print(json.dumps({'groups':[g for g in output if g['group'] in ('ChatDrug','S2-mini')],
                   'api_calls':0,'rdkit':rdkit.__version__,'output':str(ROOT)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()

