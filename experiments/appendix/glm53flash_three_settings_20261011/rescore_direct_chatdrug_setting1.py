"""Offline score-only change for saved independent GLM-direct Setting1 answers."""
import collections,hashlib,importlib.util,json,shutil,time
from pathlib import Path
import rdkit
from rdkit import RDLogger
ROOT=Path(__file__).resolve().parent
assert ROOT==Path('/data/chenfuxin/glm53flash_three_settings_20261011')
DIRECT=ROOT/'direct';SETTING='1_original_chatdrug'
OUT=DIRECT/'rescores/chatdrug_protocol_setting1_20261012'
SOURCE=Path('/data2/chenfuxin/chatdrug_generalization_20260920/upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py')
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
original=load_module('frozen_chatdrug_evaluator',SOURCE);s2=load_module('frozen_original_s2_score',DIRECT/'common.py')
RDLogger.DisableLog('rdApp.*')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
jobs=json.loads((DIRECT/'jobs.json').read_text());jobs=[x for x in jobs if x['setting']==SETTING]
assert len(jobs)==1600 and len({x['case']['id'] for x in jobs})==1600
assert collections.Counter(x['case']['property'] for x in jobs)=={'LogP':800,'QED':800}
assert collections.Counter((x['case']['property'],x['case']['constraint']) for x in jobs)=={('LogP','loose'):400,('LogP','strict'):400,('QED','loose'):400,('QED','strict'):400}
pins={str(p):sha(p) for p in [DIRECT/'jobs.json',DIRECT/'common.py',SOURCE]}
for j in jobs:
 folder=DIRECT/'runs/GLM_direct'/SETTING/j['case']['id']
 for name in ('result.json','api.json'):pins[str(folder/name)]=sha(folder/name)
rows=[];by_property=collections.defaultdict(collections.Counter);by_constraint=collections.defaultdict(collections.Counter);by_task=collections.defaultdict(collections.Counter)
for job in jobs:
 case=job['case'];path=DIRECT/'runs/GLM_direct'/SETTING/case['id']/'result.json';result=json.loads(path.read_text())
 assert result['case']==case and result['method']=='GLM_direct'
 assert case['task'] in (101,102,103,104)
 expected_thresholds=original.task2threshold_list[case['task']][case['constraint']=='strict']
 assert case['thresholds']==expected_thresholds
 assert case['instruction']==original.task_specification_dict_molecule[case['task']].replace('SMILES_PLACEHOLDER',case['smiles'])
 candidate=result.get('candidate') if result['status']=='complete' else None
 old=s2.score(case,candidate)
 assert old['success']==result['score']['success'] and old['valid']==result['score']['valid'],'Stored S2 score mismatch: '+case['id']
 before=after=None;answer=zero_answer=-1
 if candidate:
  before,after,answer=original.evaluate_molecule(case['smiles'],candidate,case['task'],case['thresholds'])
  _,_,zero_answer=original.evaluate_molecule(case['smiles'],candidate,case['task'],[0])
 valid=answer!=-1;success=bool(valid and answer);direction_only=bool(zero_answer!=-1 and zero_answer)
 delta=None if before is None or after is None else (before-after if case['task']==101 or case['task']==104 else after-before)
 counts={'expected':1,'complete':int(result['status']=='complete'),'valid_chatdrug':int(valid),'success_chatdrug':int(success),'success_s2':int(old['success']),'success_chatdrug_zero_threshold':int(direction_only),'lost_to_amplitude':int(direction_only and not success),'s2_success_chatdrug_failure':int(old['success'] and not success)}
 for group in (by_property[case['property']],by_constraint[(case['property'],case['constraint'])],by_task[(case['property'],case['task'],case['constraint'])]):group.update(counts)
 rows.append({'id':case['id'],'setting':SETTING,'property':case['property'],'task':case['task'],'constraint':case['constraint'],'thresholds':case['thresholds'],'status':result['status'],'candidate':candidate,'success_s2':old['success'],'success_chatdrug':success,'valid_chatdrug':valid,'input_property':before,'output_property':after,'signed_improvement':delta,'success_chatdrug_zero_threshold':direction_only,'source_result':str(path),'source_result_sha256':pins[str(path)]})
assert by_property['LogP']['success_s2']==743 and by_property['QED']['success_s2']==455
for p,digest in pins.items():assert sha(Path(p))==digest,'Existing source or result changed: '+p
make=lambda counts:dict(counts,accuracy_chatdrug=counts['success_chatdrug']/counts['expected'],accuracy_s2=counts['success_s2']/counts['expected'])
summary={'method':'GLM_direct','model':'glm-5.3-flash','generation':'existing independent single-response answers; no harness','setting':SETTING,'scoring_only':True,'new_model_calls':0,'expected':1600,'protocol':'Original ChatDrug evaluate_molecule with saved task-specific loose/strict thresholds; Kekulize input/output; strict comparisons; no numerical similarity cutoff; preserve existing single-final-candidate parsing and denominator','evaluator_source':str(SOURCE),'evaluator_sha256':sha(SOURCE),'rdkit_version':rdkit.__version__,'script_sha256':sha(Path(__file__)),'groups':[dict(property=k,**make(v)) for k,v in sorted(by_property.items())],'constraint_groups':[dict(property=k[0],constraint=k[1],**make(v)) for k,v in sorted(by_constraint.items())],'task_groups':[dict(property=k[0],task=k[1],constraint=k[2],**make(v)) for k,v in sorted(by_task.items())],'preservation':{'verified_unchanged_result_files':1600,'verified_unchanged_api_receipts':1600,'verified_unchanged_other_source_files':3},'updated':time.time()}
OUT.mkdir(parents=True,exist_ok=True)
shutil.copy2(SOURCE,OUT/'original_chatdrug_evaluator.py')
for name,data in [('summary.json',summary),('rows.json',rows),('preserved_source_hashes.json',pins)]:
 p=OUT/name;tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(p)
print(json.dumps({'groups':summary['groups'],'constraint_groups':summary['constraint_groups'],'preservation':summary['preservation'],'new_model_calls':0,'output':str(OUT)},ensure_ascii=False,indent=2),flush=True)
