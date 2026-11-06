"""LIDDIA controller adapted to public SMDD Type3 tasks and budgeted oracles.

Uses upstream Memory, goal parsing and decision template. Structural
changes (single submission, explicit budgeted assessments) are documented.
"""
from pathlib import Path
import argparse
import functools
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import traceback
import uuid
import pandas as pd
import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import QED, AllChem, Descriptors, Crippen, Lipinski
from rdkit.Contrib.SA_Score import sascorer
from openai import OpenAI
from smdd_liddia_tools import BudgetGate, BudgetExhausted, GraphGATool, Pocket2MolTool
from smdd_backends import ROOT, INSTALL, admet, boltz
from type3_support import prepare, Agent, TYPE3_ROOT, BASE, scaffold_mcs_fraction
from liddia_action_parser import parse_action, ActionParseError
from liddia_flow import code_prompt, validate_inputs, parse_goal, CodeExecutionError
from runtime_safety import atomic_json, ToolExecutionError, ResourceUnavailable, require_disk
from restore_liddia_state import restore

sys.path.insert(0,str(INSTALL/'LIDDIA'))
from liddia.memory import Memory
from liddia.utils import get_history_str
from liddia.prompt_template import input_fmt, check_goal_fmt, input_code_fmt

def forbidden_vina(*args, **kwargs):
    raise RuntimeError('Vina is disabled in the SMDD protocol')

for module_name,module in list(sys.modules.items()):
    if module_name.startswith('liddia.') and hasattr(module,'get_vina'):
        module.get_vina=forbidden_vina

def dump(path,data):
    atomic_json(path,data)

def rows(df):
    return json.loads(df.to_json(orient='records'))

def code_action(agent,data,desc,out):
    errors=[];source=None
    for attempt in range(3):
        response=agent.ask(code_prompt(input_code_fmt,data,desc,source,errors[-1] if errors else None),'code','You are a Python coding expert')
        match=re.search(r'```python\s*\n(.*?)```',response,re.S)
        if not match:
            errors.append('No Python block');continue
        job=out/('code_'+uuid.uuid4().hex[:12]);job.mkdir()
        source=match.group(1)
        (job/'code.py').write_text(source);dump(job/'input.json',{k:rows(v) for k,v in data.items()})
        base=INSTALL/'envs/agentd';venv=INSTALL/'envs/liddia'
        cmd=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr',
             '--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--proc','/proc','--dev','/dev',
             '--tmpfs','/tmp','--ro-bind',str(base),str(base),
             '--tmpfs',str(base/'lib/python3.11/site-packages'),
             '--ro-bind',str(venv),str(venv),
             '--tmpfs',str(venv/'lib/python3.11/site-packages/vina'),
             '--bind',str(job),'/work','--ro-bind',str(Path(__file__).with_name('code_worker.py')),'/worker.py',
             '--chdir','/work','--clearenv','--setenv','HOME','/tmp','--setenv','OMP_NUM_THREADS','1',
             '--setenv','OPENBLAS_NUM_THREADS','1',str(venv/'bin/python'),'/worker.py']
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
        except subprocess.TimeoutExpired:
            errors.append('CODE exceeded the 60 second execution limit');continue
        (job/'stderr.log').write_text(proc.stderr)
        if proc.returncode:
            errors.append(proc.stderr[-1200:]);continue
        result=pd.DataFrame(json.loads((job/'result.json').read_text()))
        if result.empty:
            result=pd.DataFrame(columns=['SMILES'])
        allowed={Chem.MolToSmiles(m) for df in data.values() for smi in df.SMILES if (m:=Chem.MolFromSmiles(smi)) is not None}
        if any(not isinstance(smi,str) or (m:=Chem.MolFromSmiles(smi)) is None or Chem.MolToSmiles(m) not in allowed for smi in result.SMILES):
            errors.append('CODE returned molecules outside its input sets; only selection/combination is allowed');continue
        return result,{'code_job':str(job),'errors':errors}
    raise CodeExecutionError('CODE failed three attempts: '+str(errors))

def main():
    p=argparse.ArgumentParser();p.add_argument('--task',default='smdd_003_1JVP_1');p.add_argument('--run',default='pilot')
    p.add_argument('--gpu',type=int,default=1);p.add_argument('--resume',action='store_true');a=p.parse_args()
    out=TYPE3_ROOT/'runs'/a.run/a.task
    if a.resume:
        derived=json.loads((out/'public/derived.json').read_text())
    else:
        out.mkdir(parents=True,exist_ok=False)
        derived=prepare(BASE/'tasks'/a.task,out/'public')
    public=json.loads((out/'public/public_task.json').read_text())
    agent=Agent(out);memory=Memory();reference=Chem.MolFromSmiles(derived['reference_smiles'])
    fp=AllChem.GetMorganFingerprintAsBitVect(reference,2,nBits=2048)
    known={};events=[];scaffold_cache={}
    def backend(kind,smi):
        value=admet(smi,out/'oracles') if kind=='admet' else boltz(smi,derived,out/'oracles',a.gpu)
        key=Chem.MolToSmiles(Chem.MolFromSmiles(smi));known.setdefault(key,{}).update(value)
        return value
    gate=BudgetGate(out/'budget.jsonl',{k:functools.partial(backend,k) for k in ('admet','boltz')},resume=a.resume)
    scorers={}
    # Objective directions/scales come from public task instructions, never evaluator feedback.
    for name,direction,threshold,baseline in re.findall(r'- (\w+): (increase|decrease) by at least ([\d.]+) from baseline ([-\d.]+)',public['description']):
        def scorer(smi,n=name,d=direction,t=float(threshold),b=float(baseline)):
            kind='boltz' if n=='binding_affinity' else 'admet'
            value=gate.predict(kind,smi)['affinity_pred_value' if kind=='boltz' else n]
            # Boltz affinity uses lower-is-better predicted log IC50; public task semantics
            # are carried by its stated direction for other properties.
            sign=-1 if kind=='boltz' or d=='decrease' else 1
            z=max(-50,min(50,sign*(value-b)/max(t,1e-6)))
            return 1/(1+math.exp(-z))
        scorers[name]=scorer
    def binding_reward(smi):
        value=float(gate.predict('boltz',smi)['affinity_pred_value'])
        return 1/(1+math.exp(max(-50,min(50,value))))
    scorers['BindingAffinity']=binding_reward
    ga=GraphGATool(scorers,seed=42)
    pocket=Pocket2MolTool(INSTALL,out/'generation',derived['center'],seed=42,device='cuda',gpu=int(os.environ.get('LIDDIA_POCKET_GPU','3')))
    actions={}
    descriptions={
      'GENERATE':"Run original Pocket2Mol to request 100 molecules conditioned on the task pocket. Input ['POCKETid']. No affinity is calculated.",
      'OPTIMIZE':"Run original GraphGA on a molecule set. Input ['MOLid','objective']. Objectives: "+str(['QED','SAScore']+list(scorers))+". Learned objectives spend the SAME ADMET/Boltz budget and stop when exhausted; QED/SA are local calculations.",
      'CODE':"Use Python to filter, combine, or select existing molecules based on known columns. Input ['MOLid', ...] and Desc. Include EVERY molecule-set ID mentioned in Desc in Input; only listed sets are passed to code. Returns molecule rows, not indices. Cannot call prediction services. Unmeasured scores are unknown.",
      'ADMET':"Predict ADMET for ONE molecule. Input ['MOLid',zero_based_row_index]. Costs one shared ADMET call, including failures.",
      'BOLTZ':"Predict binding with Boltz-2 for ONE molecule. Input ['MOLid',zero_based_row_index]. Costs one shared Boltz call, including failures. Lower affinity_pred_value is better; higher affinity_probability_binary is better. Complete predicted CIF structures are retained. Binding probability does not establish the Type3 interaction similarity condition; that remains unknown until structural assessment.",
      'SUBMIT':"Submit ONE molecule even if constraints are not satisfied. Input ['MOLid',zero_based_row_index]. Ends this task."}
    for name,desc in descriptions.items():
        key=memory.add_action(action_id=name,desc=desc,cost='1',return_id=True);actions[key]=name
    pocket_id=memory.add_pocket(filename='protein.pdb',desc='Real protein pocket derived from public complex',return_id=True)
    def enrich(df):
        records=[]
        for smi in df.SMILES:
            mol=Chem.MolFromSmiles(smi)
            if mol is None:continue
            key=Chem.MolToSmiles(mol)
            if key not in scaffold_cache:scaffold_cache[key]=scaffold_mcs_fraction(reference,mol)
            records.append({'SMILES':key,'QED':QED.qed(mol),'SAScore':sascorer.calculateScore(mol),
              'Similarity':DataStructs.TanimotoSimilarity(fp,AllChem.GetMorganFingerprintAsBitVect(mol,2,nBits=2048)),
              'ScaffoldMCS':scaffold_cache[key], 'MW':Descriptors.MolWt(mol),'LogP':Crippen.MolLogP(mol),'TPSA':Descriptors.TPSA(mol),
              'HBD':Lipinski.NumHDonors(mol),'HBA':Lipinski.NumHAcceptors(mol),**known.get(key,{})})
        return pd.DataFrame(records,columns=None if records else ['SMILES']).drop_duplicates('SMILES').reset_index(drop=True)
    def add(df,action):
        df=enrich(df)
        return memory.add_mol(data=df,action=action,metrics={},return_id=True) if len(df) else 'EMPTY SET'
    add(pd.DataFrame({'SMILES':[derived['reference_smiles']]}),'public reference')
    def context():
        parts=[]
        for key,item in memory.stream.items():
            if item['type']=='MOL':
                df=enrich(item['data']);item['data']=df
                parts.append(key+': '+json.dumps({'size':len(df),'summary':df.describe().round(4).to_dict() if len(df) else {},'rows':rows(df) if len(df)<=5 else 'Use CODE to select a subset; row indices are zero-based.'},default=str))
        return '\n'.join(parts)
    config={'task':a.task,'model':'deepseek-v4.1-flash','temperature':1.0,'seed':42,
      'enable_thinking':True,'reasoning_effort':'high','per_call_output_cap':None,
      'max_llm_calls':100,'max_tokens_total':10_000_000,'admet_budget':15,'boltz_budget':8,
      'pocket_samples':100,'pocket_beam':300,'pocket_device':'cuda','pocket_gpu':int(os.environ.get('LIDDIA_POCKET_GPU','3')),'vina_enabled':False,'gpu':a.gpu,
      'action_parser':'final_line_block_v2','flow_version':'type3_high_v1','boltz_parallel_samples':1,'pocket_snapshots':False,
      'code_hashes':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in Path(__file__).parent.glob('*.py') if x.name in ['run_liddia_type3.py','type3_support.py','liddia_action_parser.py','liddia_flow.py','smdd_backends.py','smdd_liddia_tools.py','prepare_type4.py','code_worker.py','runtime_safety.py','pocket_runtime.py','restore_liddia_state.py']}}
    dump(out/('resumed_protocol.json' if a.resume else 'protocol.json'),config)
    feedback='Unmeasured binding and interaction scores are unknown. Similarity and ScaffoldMCS are local structural measures. Binding probability alone does not establish interaction similarity. Use SUBMIT to submit your best candidate even when success is uncertain.'
    start_step=0
    if a.resume:
        start_step,feedback=restore(out,agent,memory,known,events,gate,ga,pocket,actions)
        dump(out/'resume_accounting.json',{'llm_calls':len(agent.calls),'tokens':agent.tokens,'budget_used':gate.used,'start_step':start_step})
        dump(out/'trajectory.json',events)
    status='no_submission';error=None
    try:
        for step in range(start_step,100):
            require_disk(out)
            mols=context()
            prompt=input_fmt.format(pocket_str=f'Pocket {pocket_id}: real task pocket.\n',mol_str=mols,
                action_str='\n'.join(f'{k}: {descriptions[v]}' for k,v in actions.items()),
                req_str=public['description'],history_str=get_history_str(memory),eval_str=feedback,
                resource_str=f'{100-len(agent.calls)} LLM calls; ADMET {15-gate.used["admet"]}; Boltz {8-gate.used["boltz"]}')
            response=agent.ask(prompt,'decision')
            try:
                key,inputs,desc=parse_action(response,actions)
            except ActionParseError as exc:
                feedback='Action format error: '+str(exc)+'. No tool executed. Return one final Action/Input/Desc block.'
                events.append({'step':step,'parse_error':str(exc),'budget_used':dict(gate.used)})
                dump(out/'trajectory.json',events)
                continue
            name=actions[key];meta={};result_id='NONE'
            try:
                validate_inputs(name,inputs,desc,memory.stream,pocket_id)
                if name=='GENERATE':
                    if inputs != [pocket_id]:raise ValueError('Unknown pocket')
                    df,meta=pocket(out/'public/protein.pdb',100);result_id=add(df,key)
                elif name=='OPTIMIZE':
                    df,meta=ga(memory.stream[inputs[0]]['data'],inputs[1],100,out/'optimization');result_id=add(df,key)
                elif name=='CODE':
                    df,meta=code_action(agent,{k:memory.stream[k]['data'] for k in inputs},desc,out)
                    result_id=add(df,key);inputs=inputs+[desc]
                elif name in ('ADMET','BOLTZ','SUBMIT'):
                    df=memory.stream[inputs[0]]['data'];idx=inputs[1]
                    if type(idx) is not int or not 0<=idx<len(df):raise ValueError('Invalid row index')
                    smi=df.iloc[idx]['SMILES']
                    if name=='SUBMIT':
                        (out/'solution.smi').write_text(smi+'\n');status='submitted'
                        events.append({'step':step,'action':key,'input':inputs,'submitted_smiles':smi,'budget_used':dict(gate.used)})
                        dump(out/'trajectory.json',events)
                        break
                    meta=gate.predict(name.lower(),smi);result_id=inputs[0]
                feedback=json.dumps(meta,default=str)
            except (BudgetExhausted,ValueError,ToolExecutionError) as exc:
                feedback=type(exc).__name__+': '+str(exc);meta={'error':feedback}
            history_inputs=inputs if name!='CODE' or (inputs and inputs[-1]==desc) else inputs+[desc]
            memory.add_history(action_id=key,action_input=[str(x) for x in history_inputs],action_output=result_id,metadata=meta)
            events.append({'step':step,'action':key,'input':inputs,'output':result_id,'metadata':meta,'budget_used':dict(gate.used)})
            dump(out/'trajectory.json',events)
            dump(out/'molecule_sets.json',{k:rows(v['data']) for k,v in memory.stream.items() if v['type']=='MOL'})
            if result_id in memory.stream and memory.stream[result_id]['type']=='MOL' and len(memory.stream[result_id]['data'])==1:
                goal=agent.ask(check_goal_fmt.format(mol_str=context(),req_str=public['description'])+'\nOnly answer YES when all required scores, including interaction similarity, have actually been measured for the single candidate in '+result_id+'.','goal_check')
                try:
                    answer,reason=parse_goal(goal);feedback=reason
                except ValueError as exc:
                    feedback='Goal format error: '+str(exc);continue
                if answer.strip()=='YES':
                    (out/'solution.smi').write_text(memory.stream[result_id]['data'].iloc[0]['SMILES']+'\n');status='submitted';break
    except BudgetExhausted as exc:
        status='budget_exhausted';error=str(exc)
    except ResourceUnavailable as exc:
        status='resource_blocked';error=str(exc)
    except Exception as exc:
        status='runtime_error';error=traceback.format_exc()
    dump(out/'agent_result.json',{'status':status,'error':error,'llm_calls':len(agent.calls),'tokens':agent.tokens,'budget_used':gate.used,'vina_calls':0})
    print(json.dumps({'status':status,'output':str(out),'budget_used':gate.used}))

if __name__=='__main__':main()
