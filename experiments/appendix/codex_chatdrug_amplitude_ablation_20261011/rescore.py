"""Offline Codex amplitude ablation; frozen official protocol, existing final outputs only."""
from pathlib import Path
import collections,copy,hashlib,json,sys,time,os
import rdkit
from rdkit import RDLogger
ROOT=Path(__file__).resolve().parent
BASE=Path('/data/chenfuxin/codex_chatdrug_molopt_loopguard_c16_resume2_20261011')
REFERENCE=Path('/data2/chenfuxin/chatdrug_amplitude_ablation_20261005/summary.json')
SOL_REFERENCE=Path('/data/chenfuxin/sol_pi_chatdrug_amplitude_ablation_20261008/rescore.py')
sys.path.insert(0,str(BASE))
import score

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):
 tmp=p.with_suffix('.tmp')
 with tmp.open('w') as f:
  json.dump(d,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 tmp.replace(p)
def main():
 assert not (ROOT/'summary.json').exists(),'Existing evaluation is preserved'
 reference=json.loads(REFERENCE.read_text());evaluate,p=score.original_evaluator()
 assert rdkit.__version__==reference['rdkit_version']=='2022.09.4'
 assert sha(Path(p.SM.__file__))==reference['evaluator_sha256']
 RDLogger.DisableLog('rdApp.*')
 combined_path=BASE/'combined_latest_7100.json';combined_hash=sha(combined_path);combined=json.loads(combined_path.read_text())
 assert combined['phase']=='complete'
 source_rows={r['id']:r for r in combined['rows'] if r['benchmark']=='ChatDrug'}
 cases=[c for c in json.loads((BASE/'original_cases.json').read_text()) if c['benchmark']=='ChatDrug']
 assert len(cases)==len(source_rows)==len({c['id'] for c in cases})==5600
 assert {c['id'] for c in cases}==set(source_rows)
 groups=collections.defaultdict(collections.Counter);rows=[];hashes={};evaluations={};started=time.time()
 for i,case in enumerate(cases,1):
  stored=source_rows[case['id']];source=Path(stored['result_path']);evaluation=Path(stored['evaluation_path'])
  hashes[str(source)]=sha(source);evaluations[str(evaluation)]=sha(evaluation);generation=json.loads(source.read_text());e=json.loads(evaluation.read_text())
  assert e['protocol']=='original' and e['evaluation_calls']==1
  assert generation['id']==case['id'] and generation['status']==stored['result']['status']
  complete=generation['status']=='complete';candidate=generation.get('candidate') if complete else None
  original=evaluate(case,candidate)
  assert original==stored['score']==e['score'],case['id']
  zero=copy.deepcopy(case);zero['thresholds']=[0]*len(case['objectives']);new=evaluate(zero,candidate)
  assert original['valid']==new['valid'],case['id']
  assert not original['success'] or new['success'],case['id']
  signed_delta_success=bool(original['valid'] and original.get('property_deltas') and all(d>0 for d in original['property_deltas']))
  assert new['success']==signed_delta_success,case['id']
  if all(t==0 for t in case['thresholds']):assert new['success']==original['success'],case['id']
  labels=['ChatDrug','ChatDrug_'+case['constraint'],'task_'+str(case['task']),'task_'+str(case['task'])+'_'+case['constraint'],'ChatDrug_single' if len(case['objectives'])==1 else 'ChatDrug_multi']
  for label in labels:
   g=groups[label];g['expected']+=1;g['complete']+=complete;g['valid']+=new['valid'];g['original_success']+=original['success'];g['direction_only_success']+=new['success']
  rows.append({'id':case['id'],'task':case['task'],'constraint':case['constraint'],'status':generation['status'],'candidate':candidate,'source':str(source),'harness_variant':stored['harness_variant'],'original_score':original,'direction_only_score':new})
  if i%500==0:
   state={'phase':'scoring','processed':i,'expected':5600,'elapsed_seconds':time.time()-started,'original_success':groups['ChatDrug']['original_success'],'direction_only_success':groups['ChatDrug']['direction_only_success'],'api_calls':0}
   dump(ROOT/'progress.json',state);print(json.dumps(state),flush=True)
 summary_groups={}
 for label,counts in groups.items():
  g=dict(counts);g.update(original_rate=g['original_success']/g['expected'],direction_only_rate=g['direction_only_success']/g['expected'],rescued=g['direction_only_success']-g['original_success']);summary_groups[label]=g
 assert summary_groups['ChatDrug']['original_success']==3410
 assert summary_groups['ChatDrug_loose']['expected']==summary_groups['ChatDrug_strict']['expected']==2800
 assert summary_groups['ChatDrug_loose']['direction_only_success']==summary_groups['ChatDrug_loose']['original_success']
 assert sha(combined_path)==combined_hash
 assert all(sha(Path(file))==digest for file,digest in hashes.items())
 assert all(sha(Path(file))==digest for file,digest in evaluations.items())
 report={'method':'codex','model':'deepseek-v4.1-flash','protocol':reference['protocol'],'expected':5600,'input_combined':str(combined_path),'input_combined_sha256':combined_hash,'case_sha256':sha(BASE/'original_cases.json'),'evaluator_sha256':sha(Path(p.SM.__file__)),'reference_summary':str(REFERENCE),'reference_script_sha256':sha(REFERENCE.with_name('rescore.py')),'sol_pi_reference_script_sha256':sha(SOL_REFERENCE),'rdkit_version':rdkit.__version__,'script_sha256':sha(Path(__file__)),'source_result_sha256':hashes,'source_evaluation_sha256':evaluations,'groups':summary_groups,'harness_variants':dict(collections.Counter(r['harness_variant'] for r in rows)),'api_calls':0,'validation':{'reproduced_original_scores':5600,'all_previous_successes_retained':True,'zero_threshold_matches_independent_signed_deltas':True,'loose_scores_unchanged':True,'inputs_unchanged':True},'time':time.time(),'elapsed_seconds':time.time()-started}
 dump(ROOT/'rows.json',rows);dump(ROOT/'summary.json',report);dump(ROOT/'progress.json',{'phase':'complete','processed':5600,'expected':5600,'time':time.time(),'api_calls':0})
 print(json.dumps({'overall':summary_groups['ChatDrug'],'loose':summary_groups['ChatDrug_loose'],'strict':summary_groups['ChatDrug_strict'],'single':summary_groups['ChatDrug_single'],'multi':summary_groups['ChatDrug_multi'],'rdkit_version':rdkit.__version__,'api_calls':0,'output':str(ROOT)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
