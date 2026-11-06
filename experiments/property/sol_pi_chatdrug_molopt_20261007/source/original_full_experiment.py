"""Full 28-setting source + all 1500 target cases; restartable sequential tmux job."""
import argparse, collections, csv, datetime, fcntl, functools, json, pathlib, sys, time
import pilot as p
from deepseek_check import config

ROOT=p.ROOT
PREP=ROOT/'prepared_full'
OUT=ROOT/'runs/deepseek_full'
TASKS={101:[('LogP',-1)],102:[('LogP',1)],103:[('QED',1)],104:[('QED',-1)],
       105:[('TPSA',-1)],106:[('TPSA',1)],107:[('HBA',1)],108:[('HBD',1)]}
for task,parts in {201:(101,107),202:(102,107),203:(101,108),204:(102,108),205:(101,105),206:(101,106)}.items():
    TASKS[task]=sum((TASKS[t] for t in parts),[])

@functools.lru_cache(maxsize=40000)
def properties(smiles,kekulize):
    mol=p.Chem.MolFromSmiles(smiles)
    if kekulize:p.Chem.Kekulize(mol)
    return {name:fn(mol) for name,fn in [('LogP',p.Descriptors.MolLogP),('QED',p.Descriptors.qed),
        ('TPSA',p.Descriptors.TPSA),('HBA',p.Descriptors.NumHAcceptors),('HBD',p.Descriptors.NumHDonors),('MR',p.Descriptors.MolMR)]}

def retrieval_success(case,candidate):
    source=case['benchmark']=='ChatDrug'
    original=properties(case['smiles'],source);modified=properties(candidate,source)
    return all((modified[prop]>original[prop]+threshold if direction==1 else modified[prop]+threshold<original[prop])
        for (prop,direction),threshold in zip(case['objectives'],case['thresholds']))

def score(case,candidate):
    invalid={'valid':False,'success':False,'similarity':None,'delta':None,'candidate':candidate}
    if not candidate or p.Chem.MolFromSmiles(candidate) is None:return invalid
    if case['benchmark']=='ChatDrug':
        original,modified,answer=p.SM.evaluate_molecule(case['smiles'],candidate,case['task'],case['thresholds'])
        if answer==-1:return invalid
        success=bool(answer)
        orig=list(original) if isinstance(original,tuple) else [original]
        mod=list(modified) if isinstance(modified,tuple) else [modified]
    else:
        name={'LogP':'logP','QED':'qed','MR':'MR'}[case['property']]
        orig=[p.S2_PROP(case['smiles'],name)];mod=[p.S2_PROP(candidate,name)]
        success=mod[0]>orig[0] if case['direction']=='higher' else mod[0]<orig[0]
    deltas=[float((b-a)*direction) for a,b,(_,direction) in zip(orig,mod,case['objectives'])]
    return {'valid':True,'success':success,'similarity':float(p.S2_SIM(case['smiles'],candidate)),
        'delta':deltas[0] if len(deltas)==1 else None,'property_deltas':deltas,'candidate':candidate,
        'input_property':orig,'output_property':mod}

def install():
    p.env_config=config;p.score=score;p.retrieval_success=retrieval_success
    p.load_functions(ROOT/'full_case.py',['run_case'],p.__dict__)

def prepare():
    PREP.mkdir(exist_ok=True)
    src=ROOT/'data/ChatDrug_data/small_molecule/small_molecule_editing.txt'
    source=list(dict.fromkeys(src.read_text().splitlines()));assert len(source)==200
    cases=[];excluded={p.canonical(s) for s in source};hashes={'source':p.sha(src)}
    for task,objectives in TASKS.items():
        for setting,thresholds in zip(('loose','strict'),p.SM.task2threshold_list[task]):
            for i,smiles in enumerate(source):
                cases.append({'id':f'source_{task}_{setting}_{i:03d}','benchmark':'ChatDrug','task':task,
                    'property':'+'.join(x[0] for x in objectives),'direction':'multi' if len(objectives)>1 else ('higher' if objectives[0][1]==1 else 'lower'),
                    'objectives':objectives,'thresholds':thresholds,'constraint':setting,'smiles':smiles,
                    'instruction':p.SM.task_specification_dict_molecule[task].replace('SMILES_PLACEHOLDER',smiles)})
    for prop in ('LogP','QED','MR'):
        path=ROOT/'data/S2-TOMG-Bench-mini'/f'MolOpt_{prop}.csv'
        rows=list(csv.DictReader(path.open()));assert len(rows)==500;hashes[prop]=p.sha(path)
        for i,row in enumerate(rows):
            direction='lower' if any(w in row['Instruction'].lower() for w in ('lower','decrease')) else 'higher'
            # Task ID only selects molecular parser and similarity; MR scoring is an explicit new adapter.
            task=({'LogP':(101,102),'QED':(104,103),'MR':(101,102)}[prop])[direction=='higher']
            cases.append({'id':f's2_{prop}_{row["index"]}','benchmark':'S2-mini','task':task,'property':prop,
                'direction':direction,'objectives':[(prop,1 if direction=='higher' else -1)],'thresholds':[0],
                'constraint':'loose','smiles':row['molecule'],'instruction':row['Instruction'],'original_row':i,'original_index':row['index']})
            excluded.add(p.canonical(row['molecule']))
    corpuspath=ROOT/'data/ChatDrug_data/small_molecule/250k_rndm_zinc_drugs_clean_3.csv'
    clean=[];seen=set();removed=invalid=duplicates=0
    for smiles in p.pd.read_csv(corpuspath)['smiles']:
        smiles=smiles.strip();canonical=p.canonical(smiles)
        if canonical is None:invalid+=1;continue
        if canonical in excluded:removed+=1;continue
        if canonical in seen:duplicates+=1;continue
        seen.add(canonical);clean.append(smiles)
    db=p.pd.DataFrame({'sequence':clean}).sample(10000,random_state=0).reset_index(drop=True)
    db.to_csv(PREP/'retrieval.csv',index=False);p.dump(PREP/'cases.json',cases)
    manifest={'source_cases':5600,'target_cases':1500,'total_cases':len(cases),'source_inputs':200,
        'source_settings':28,'target_per_property':500,'input_hashes':hashes,'corpus_sha256':p.sha(corpuspath),
        'excluded_unique_structures':len(excluded),'excluded_rows':removed,'invalid_rows':invalid,'duplicates':duplicates,
        'canonical_test_retrieval_overlap':sum(p.canonical(s) in excluded for s in db.sequence),
        'retrieval_rows':len(db),'retrieval_sha256':p.sha(PREP/'retrieval.csv'),
        'note':'New full-experiment retrieval corpus excludes MR too; pilot results not pooled. MR is an adapter extension, not an original ChatDrug task.'}
    assert len(cases)==7100 and len({c['id'] for c in cases})==7100 and manifest['canonical_test_retrieval_overlap']==0
    p.dump(PREP/'manifest.json',manifest);p.emit({'prepared':manifest})

def validate():
    cases=json.loads((PREP/'cases.json').read_text());db=p.pd.read_csv(PREP/'retrieval.csv')
    representatives={}
    for c in cases:representatives.setdefault((c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction']),c)
    checks=0
    for c in representatives.values():
        for s in [c['smiles']]+list(db.sequence.iloc[:50]):
            r=score(c,s)
            assert r['success']==retrieval_success(c,s),(c['id'],s)
            if c['benchmark']=='S2-mini':
                prop={'LogP':'logP','QED':'qed','MR':'MR'}[c['property']]
                assert properties(s,False)[c['property']]==p.S2_PROP(s,prop)
            checks+=1
        assert not score(c,'INVALID')['valid']
        assert not score(c,c['smiles'])['success']
    # Check every original strict boundary with identical arithmetic to upstream.
    assert {c['task'] for c in cases if c['benchmark']=='ChatDrug'}==set(p.SM.task_specification_dict_molecule)
    assert collections.Counter(c['benchmark'] for c in cases)=={'ChatDrug':5600,'S2-mini':1500}
    p.dump(PREP/'validation.json',{'passed':True,'evaluation_equivalence_checks':checks,'representatives':len(representatives),'invalid_and_identity_checked':True})
    p.emit({'validation':'passed','checks':checks})

def summarize():
    rows=[json.loads(f.read_text()) for f in sorted(OUT.glob('*/result.json'))]
    groups=collections.defaultdict(list)
    for r in rows:
        c=r['case'];groups[(c['benchmark'],str(c['task']) if c['benchmark']=='ChatDrug' else c['property'],c['constraint'])].append(r)
    metrics=[]
    for (bench,task,setting),rs in sorted(groups.items()):
        for arm in ('direct','chatdrug','independent3'):
            values=[r['arms'][arm] for r in rs if r['status']=='complete']
            valid=[v for v in values if v['valid']]
            metrics.append({'benchmark':bench,'task':task,'setting':setting,'arm':arm,'completed':len(values),
                'errors':sum(r['status']!='complete' for r in rs),'expected':200 if bench=='ChatDrug' else 500,
                'successes':sum(v['success'] for v in values),'success_rate_completed':sum(v['success'] for v in values)/len(values) if values else None,
                'validity':len(valid)/len(values) if values else None,'similarity_valid':sum(v['similarity'] for v in valid)/len(valid) if valid else None})
    complete=[r for r in rows if r['status']=='complete']
    official={f'{arm}_{prop}':p.official_target_check(complete,arm,prop) for arm in ('direct','chatdrug','independent3') for prop in ('LogP','QED','MR')}
    result={'expected':7100,'complete':len(complete),'errors':len(rows)-len(complete),
        'requests':sum(r['api_requests'] for r in rows),'retries':sum(r['retry_attempts'] for r in rows),
        'refusals':sum(r.get('refusals',0) for r in rows),'official_target_crosscheck':official,'groups':metrics}
    p.dump(OUT/'summary.json',result)
    if metrics:
        with (OUT/'metrics.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(metrics[0]));writer.writeheader();writer.writerows(metrics)
    return result

def run():
    OUT.mkdir(exist_ok=True,parents=True)
    lock=(OUT/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    validate()
    cases=json.loads((PREP/'cases.json').read_text());db=p.pd.read_csv(PREP/'retrieval.csv')
    # First exercise all 28 source settings plus both directions of all three target properties.
    buckets=collections.defaultdict(list)
    for c in cases:buckets[(c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction'])].append(c)
    ordered=[items[i] for i in range(max(map(len,buckets.values()))) for items in buckets.values() if i<len(items)]
    hashes={f:p.sha(ROOT/f) for f in ('full_experiment.py','full_case.py','pilot.py','deepseek_check.py')}
    cfg={'model':'deepseek-flash','provider':'official DeepSeek','workers':1,'thinking':'disabled','effort':'low','temperature':0,
        'max_tokens':2048,'feedback_rounds':2,'arms':['direct','chatdrug','independent3'],'shared_initial':True,
        'expected':7100,'code_hashes':hashes,'manifest_sha256':p.sha(PREP/'manifest.json'),
        'retry_policy':'up to 3 HTTP attempts; no retry for refusal; halt on 2 case infrastructure errors',
        'MR':'new property adapter; unchanged retrieval and conversation algorithm','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    path=OUT/'run_config.json'
    if path.exists():
        previous=json.loads(path.read_text());assert previous['code_hashes']==hashes and previous['manifest_sha256']==cfg['manifest_sha256'],'Refuse incompatible resume'
    else:p.dump(path,cfg)
    errors=0;start=time.monotonic()
    for i,c in enumerate(ordered,1):
        existing=OUT/c['id']/'result.json'
        # Preserve errored records on resume; do not silently overwrite or repeatedly bill them.
        r=json.loads(existing.read_text()) if existing.exists() else p.run_case(c,db,OUT)
        errors+=r['status']!='complete'
        p.dump(OUT/'progress.json',{'processed':i,'expected':7100,'errors':errors,'last_case':c['id'],
            'elapsed_seconds':round(time.monotonic()-start),'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        if i==len(buckets):
            p.dump(OUT/'gate.json',{'cases':i,'passed':errors==0,'errors':errors})
            if errors:break
        if i%100==0:summarize()
        if errors>=2:break
    summary=summarize();p.emit({k:v for k,v in summary.items() if k not in ('groups','official_target_crosscheck')})
    if summary['complete']!=7100 or summary['errors']:raise SystemExit(2)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','validate','run','summary']);args=parser.parse_args()
    install()
    {'prepare':prepare,'validate':validate,'run':run,'summary':summarize}[args.action]()
