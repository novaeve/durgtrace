"""Score one final SMILES per frozen instance; missing/failed cases remain failures."""
from pathlib import Path
import argparse,ast,collections,copy,csv,functools,importlib.util,json,re,sys,types,typing
ROOT=Path(__file__).resolve().parents[1]
PROPERTY=ROOT/'experiments/property/chatdrug_generalization_20260920'
S2=ROOT/'experiments/structural/s2_edit_custom_20260928'
LANG=ROOT/'experiments/structural/mollangbench_20260928'
TASKS={'cd28':5600,'cd28_logp':800,'cd28_qed':800,'s2_molopt':1500,'s2_logp':500,'s2_qed':500,'s2_mr':500,'s2_edit':1500,'s2_custom':1500,'mollang_edit':400,'mollang_generation':400}

def functions(path,names,ns):
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    if {n.name for n in nodes}!=set(names):raise ValueError('Frozen function not found: '+str(path))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns);return ns

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Scorer:
    def __init__(self):
        from rdkit import Chem,DataStructs,RDLogger
        from rdkit.Chem import AllChem,Descriptors
        RDLogger.DisableLog('rdApp.*')
        self.Chem=Chem
        ns={'Chem':Chem,'DataStructs':DataStructs,'AllChem':AllChem,'Descriptors':Descriptors}
        functions(S2/'source/s2_properties.py',['mol_prop','smiles_to_fingerprint','calculate_similarity'],ns)
        self.s2_prop=ns['mol_prop']
        sm=module('frozen_chatdrug_evaluator',PROPERTY/'upstream/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py')
        proxy=types.SimpleNamespace(Chem=Chem,Descriptors=Descriptors,SM=sm,S2_PROP=ns['mol_prop'],S2_SIM=ns['calculate_similarity'])
        self.property_ns=functions(PROPERTY/'full_experiment.py',['score'],{'p':proxy})
        # Load the exact frozen functions with an explicit UTF-8 reader, avoiding locale-dependent
        # Linux transport imports on Windows. Their scientific bodies and constants stay unchanged.
        s2ns=dict(ns,ROOT=S2,csv=csv,functools=functools)
        tree=ast.parse((S2/'benchmark.py').read_text(encoding='utf-8'))
        constants=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'ATOMS','GROUPS','BONDS'} for t in n.targets)]
        exec(compile(ast.Module(body=constants,type_ignores=[]),str(S2/'benchmark.py'),'exec'),s2ns)
        functions(S2/'benchmark.py',['cases','constraints','evaluate','fingerprint'],s2ns)
        self.s2=types.SimpleNamespace(**s2ns)
        ns2={'Chem':Chem,'re':re,'Optional':typing.Optional}
        functions(LANG/'upstream/MolLangBench-main/scripts/evaluate_results.py',['canonicalize_smiles','parse_smiles_from_output'],ns2)
        self.canonical=ns2['canonicalize_smiles']
        self.answers=json.loads((LANG/'data/answers.json').read_text(encoding='utf-8'))

    def cases(self,task):
        if task.startswith(('cd28','s2_')) and task not in {'s2_edit','s2_custom'}:
            rows=json.loads((PROPERTY/'prepared_full/cases.json').read_text(encoding='utf-8'))
            rows=[c for c in rows if c['benchmark']==('ChatDrug' if task.startswith('cd28') else 'S2-mini')]
            prop={'cd28_logp':'LogP','cd28_qed':'QED','s2_logp':'LogP','s2_qed':'QED','s2_mr':'MR'}.get(task)
            if prop:rows=[c for c in rows if c['property']==prop]
        elif task in {'s2_edit','s2_custom'}:rows=[c for c in self.s2.cases() if c['task']==('MolEdit' if task=='s2_edit' else 'MolCustom')]
        else:rows=[c for c in json.loads((LANG/'data/cases.json').read_text(encoding='utf-8')) if c['task']==('edit' if task=='mollang_edit' else 'generation')]
        if len(rows)!=TASKS[task] or len({c['id'] for c in rows})!=len(rows):raise ValueError('Frozen task set count/identity mismatch')
        return rows

    def score(self,task,case,candidate,protocol='native'):
        if task.startswith(('cd28','s2_')) and task not in {'s2_edit','s2_custom'}:
            c=copy.deepcopy(case)
            if protocol=='direction-native':
                if not task.startswith('cd28'):raise ValueError('direction-native is a ChatDrug rescoring protocol')
                c['thresholds']=[0]*len(c['thresholds'])
            elif protocol=='direction-s2':
                if task not in {'cd28_logp','cd28_qed'}:raise ValueError('direction-s2 is restricted to the A6/B1 LogP or QED subset')
                c.update(benchmark='S2-mini',thresholds=[0])
            return self.property_ns['score'](c,candidate)
        if protocol!='native':raise ValueError('Rescoring variants apply to ChatDrug property cases only')
        if task in {'s2_edit','s2_custom'}:return self.s2.evaluate(case,candidate)
        pred=self.canonical(candidate or '');gold=self.canonical(self.answers[case['id']])
        return {'valid_official':pred is not None,'valid_nonempty':bool(pred),'success':pred is not None and pred==gold}

def score_records(task,records,protocol='native'):
    scorer=Scorer();cases=scorer.cases(task);by_id={};expected={c['id'] for c in cases}
    for row in records:
        if row['id'] in by_id:raise ValueError('Duplicate final output: '+row['id'])
        if row['id'] not in expected:raise ValueError('Unknown case ID: '+row['id'])
        by_id[row['id']]=row
    scored=[]
    for case in cases:
        row=by_id.get(case['id']);candidate=row.get('candidate') if row and row.get('status','complete')=='complete' else None
        try:result=scorer.score(task,case,candidate,protocol)
        except Exception as e:result={'success':False,'evaluation_error':type(e).__name__}
        scored.append({'id':case['id'],'supplied':row is not None,'runtime_status':row.get('status','complete') if row else 'missing','candidate':candidate,'score':result})
    success=sum(bool(r['score']['success']) for r in scored)
    import rdkit
    return {'task':task,'protocol':protocol,'expected':len(cases),'supplied':len(records),'successes':success,'success_rate':success/len(cases),'rdkit_version':rdkit.__version__,'evaluation_errors':sum('evaluation_error' in r['score'] for r in scored),'rows':scored,'note':'Rescores saved final outputs only; does not generate or select alternatives. Published values require the recorded original RDKit environment.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',choices=TASKS,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--protocol',choices=['native','direction-native','direction-s2'],default='native');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.protocol=='direction-s2' and a.task not in {'cd28_logp','cd28_qed'}:p.error('direction-s2 requires cd28_logp or cd28_qed')
    if a.protocol=='direction-native' and not a.task.startswith('cd28'):p.error('direction-native requires a cd28 task')
    records=[json.loads(line) for line in a.predictions.read_text(encoding='utf-8').splitlines() if line.strip()]
    result=score_records(a.task,records,a.protocol);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
