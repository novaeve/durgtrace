"""Create a separate, frozen Type3 experiment without touching active Type4."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import time

INSTALL=Path('/data2/chenfuxin/agent_reproduction_20260928')
BASE=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')
ROOT=Path('/data2/chenfuxin/liddia_smdd_type3_20261004')
assert not ROOT.exists(),'Existing experiment must be reconciled rather than overwritten'
ROOT.mkdir();source=ROOT/'source'
shutil.copytree(Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3/source'),source)
for name in ('parallel_type4.py','run_type4_batch.py'):(source/name).unlink()
for name in ('type3_support.py','evaluate_liddia_type3.py','type3_eval_bridge.py','run_type3_batch.py','type3_preflight.py'):
    shutil.copy2(INSTALL/name,source/name)
controller=(source/'run_liddia_type4.py').read_text()
def change(old,new):
    global controller
    assert controller.count(old)==1,(old,controller.count(old))
    controller=controller.replace(old,new)
controller=controller.replace('SMDD Type4','SMDD Type3')
change('from prepare_type4 import prepare','from type3_support import prepare, Agent, TYPE3_ROOT, BASE, scaffold_mcs_fraction')
start=controller.index('class Agent:');end=controller.index('def code_action(',start)
controller=controller[:start]+controller[end:]
change("default='smdd_004_ABL1_1'","default='smdd_003_1JVP_1'")
change("out=ROOT/'runs'/a.run/a.task","out=TYPE3_ROOT/'runs'/a.run/a.task")
change("derived=prepare(ROOT/'benchmark/tasks'/a.task,out/'public')","derived=prepare(BASE/'tasks'/a.task,out/'public')")
change('known={};events=[]','known={};events=[];scaffold_cache={}')
change("key=Chem.MolToSmiles(mol)\n            records.append", "key=Chem.MolToSmiles(mol)\n            if key not in scaffold_cache:scaffold_cache[key]=scaffold_mcs_fraction(reference,mol)\n            records.append")
change("'MW':Descriptors.MolWt(mol)","'ScaffoldMCS':scaffold_cache[key], 'MW':Descriptors.MolWt(mol)")
change("'max_llm_calls':100,","'enable_thinking':True,'reasoning_effort':'high','per_call_output_cap':None,\n      'max_llm_calls':100,")
change("'runtime_wait_restore_v3'","'type3_high_v1'")
change("'run_liddia_type4.py','liddia_action_parser.py'","'run_liddia_type3.py','type3_support.py','liddia_action_parser.py'")
change("Lower affinity_pred_value is better; higher affinity_probability_binary is better.",
       "Lower affinity_pred_value is better; higher affinity_probability_binary is better. Complete predicted CIF structures are retained. Binding probability does not establish the Type3 interaction similarity condition; that remains unknown until structural assessment.")
change("feedback='Unmeasured ADMET and binding values are unknown. Do not infer them from QED or SA.'",
       "feedback='Unmeasured binding and interaction scores are unknown. Similarity and ScaffoldMCS are local structural measures. Binding probability alone does not establish interaction similarity. Use SUBMIT to submit your best candidate even when success is uncertain.'")
change("Only answer YES when all required learned scores have actually been measured for the single candidate in ",
       "Only answer YES when all required scores, including interaction similarity, have actually been measured for the single candidate in ")
(source/'run_liddia_type3.py').write_text(controller)
(source/'run_liddia_type4.py').unlink()
# Same Boltz prediction; retain the complete result directory for official Type3 scoring.
p=source/'smdd_backends.py';backend=p.read_text()
old="return json.loads((job/'out/boltz_results_input/predictions/input/affinity_input.json').read_text())"
assert backend.count(old)==1
backend=backend.replace(old,"result=json.loads((job/'out/boltz_results_input/predictions/input/affinity_input.json').read_text())\n        result['prediction_directory']=str(job/'out')\n        return result")
backend=backend.replace('def boltz_payload(payload, output, gpu=1, samples=10, seed=42):',
                        "def boltz_payload(payload, output, gpu=1, samples=10, seed=42, job_name='input'):\n    if Path(job_name).name!=job_name or not job_name or job_name in ('.','..'):raise ValueError('Invalid job name')")
backend=backend.replace("job/'input.yaml'","job/(job_name+'.yaml')")
backend=backend.replace("job/'out/boltz_results_input/predictions/input/affinity_input.json'", "job/'out'/('boltz_results_'+job_name)/'predictions'/job_name/('affinity_'+job_name+'.json')")
p.write_text(backend)
for p in source.glob('*.py'):ast.parse(p.read_text())
tasks=(BASE/'task_list.txt').read_text().split();assert len(tasks)==52 and len(set(tasks))==52
reference=json.loads(Path('/data2/chenfuxin/smdd_type3_harness_20261001/manifest.json').read_text())
for key,value in {'model':'deepseek-v4.1-flash','enable_thinking':True,'reasoning_effort':'high','temperature':1,
                  'max_calls':100,'cumulative_token_budget':10000000,'boltz_budget':8,'admet_budget':15,
                  'per_call_output_cap':None}.items():assert reference[key]==value,key
manifest={**{k:reference[k] for k in ('model','enable_thinking','reasoning_effort','temperature','max_calls',
          'cumulative_token_budget','boltz_budget','admet_budget','per_call_output_cap','official_commit')},
          'created':time.time(),'tasks':tasks,'method':'LIDDIA Type3 adaptation',
          'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')},
          'task_hashes':{t:hashlib.sha256((BASE/'tasks'/t/'task.yaml').read_bytes()).hexdigest() for t in tasks},
          'common_runtime_sha256':hashlib.sha256((BASE/'runtime.py').read_bytes()).hexdigest(),
          'public_obfuscation_sha256':hashlib.sha256((BASE/'upstream/agent_harness/obfuscate.py').read_bytes()).hexdigest(),
          'official_evaluation_hashes':{str(p.relative_to(BASE/'upstream')):hashlib.sha256(p.read_bytes()).hexdigest()
                                        for folder in ('metrics','evaluator') for p in (BASE/'upstream'/folder).rglob('*.py')},
          'sampling':{'seed':42,'diffusion_samples':10,'affinity_samples':10,'max_parallel_samples':1,
                      'pocket_samples':100,'pocket_beam':300,'pocket_checkpoint_sha256':hashlib.sha256((INSTALL/'Pocket2Mol/ckpt/pretrained_Pocket2Mol.pt').read_bytes()).hexdigest()},
          'gpus':[5,7],'vina_enabled':False,'generation_feedback_uses_hidden_gt':False,
          'note':'Same high-thinking model boundary and benchmark protocol; native LIDDIA planner/memory/Pocket2Mol/GraphGA are the agent differences.'}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
(ROOT/'实验协议.md').write_text('''# LIDDIA SMDD Type3

使用与服务器已有五组相同的52题和同一百炼端点，deepseek-v4.1-flash、enable_thinking=true、reasoning_effort=high、temperature=1；对齐官方 harness / Codex / MolClaw，不设置单次输出 token 上限。每题最多100次模型请求、累计1000万输入输出token，ADMET15次、Boltz8次。CODE和目标检查的模型请求同样计入。原始请求、完整响应及思考token均保存，不记录密钥。

保留LIDDIA原作者Memory、决策提示模板和动作规划，沿已有解析器和代码错误反馈修复；生成工具为原Pocket2Mol公开预训练权重，每次100个分子、beam300、真实公开蛋白口袋，优化为原GraphGA。Vina禁用。GraphGA的学习型评分与直接BOLTZ/ADMET共用预算，失败调用也计入。公开Similarity/ScaffoldMCS按官方定义计算，不强制预过滤候选，不用隐藏评分反馈筛选。三维相互作用未测定时保持未知。

公开文件沿现有obfuscate_task去标识，仅complex.pdb、reference.sdf；结构派生序列和口袋中心只取公开文件。隐藏ground_truth_docked.sdf、gt_results、评分条件只进入独立官方评测。Boltz保留全部CIF/置信度/亲和力输出，结构和affinity各10样本、seed42，最大同时采样1及expandable_segments与现有OOM修复后的评测配置一致。

这是LIDDIA跨任务迁移，不声称论文原模型的原任务复现。模型配置、任务及评分对齐；Pocket2Mol/GraphGA与规划流程属于agent差异，既有ChatDrug/AgentDrug自身生成轮次上限不因本实验改变。现有五组和Type4结果保留。正式全量52题独立目录runs/full_high_v1，诊断验证smoke独立保存。基础设施失败不作为科学未达标；不自动重置预算或重抽结果。两路使用GPU5/7，不改变Type4三路队列。
''')
print(json.dumps({'root':str(ROOT),'tasks':52,'source_modules':len(manifest['source_hashes']),'thinking':'high','gpus':[5,7]}))
