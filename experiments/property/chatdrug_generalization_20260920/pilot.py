"""Frozen ChatDrug functions + Claude relay adapter; source/target pilot only."""
import argparse, ast, collections, concurrent.futures, contextlib, csv, functools
import hashlib, importlib.util, io, json, os, pathlib, random, sys, threading, time
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd
import requests
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem, Descriptors
import rdkit

ROOT=pathlib.Path(__file__).resolve().parent
CD=ROOT/'upstream/ChatDrug'
S2=ROOT/'upstream/S2-TOMG-Bench'
SEED=20260920
RDLogger.DisableLog('rdApp.*')
PRINT_LOCK=threading.Lock()

def emit(value):
    with PRINT_LOCK:print(json.dumps(value,ensure_ascii=False,default=str),flush=True)

def dump(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    temp.replace(path)

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def load_functions(path,names,namespace):
    tree=ast.parse(pathlib.Path(path).read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    if {n.name for n in nodes}!=set(names):raise RuntimeError('Missing upstream functions')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace

spec=importlib.util.spec_from_file_location('upstream_small_molecule',CD/'ChatDrug/task_and_evaluation/small_molecule_editing.py')
SM=importlib.util.module_from_spec(spec);spec.loader.exec_module(SM)
S2NS=load_functions(S2/'utils/evaluation.py',['smiles_to_fingerprint','calculate_similarity','mol_prop'],
    {'Chem':Chem,'AllChem':AllChem,'DataStructs':DataStructs,'Descriptors':Descriptors})
S2_PROP=S2NS['mol_prop']
S2_SIM=S2NS['calculate_similarity']

def env_config():
    d={}
    for line in (ROOT/'private/Claude.env').read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            k,v=line.split('=',1);d[k.strip().removeprefix('export ')]=v.strip().strip('\"').strip("'")
    if not all(d.get(k) for k in ['ANTHROPIC_API_KEY','ANTHROPIC_BASE_URL','ANTHROPIC_MODEL']):
        raise RuntimeError('Missing relay configuration fields')
    return d

class RelayError(Exception):pass

def decode_sse(lines):
    result={};blocks={}
    for line in lines:
        if isinstance(line,bytes):line=line.decode('utf-8')
        if not line.startswith('data:'):continue
        raw=line[5:].strip()
        if raw=='[DONE]':break
        event=json.loads(raw);kind=event.get('type')
        if kind=='message_start':result=event['message'];result['usage']=dict(result.get('usage',{}))
        elif kind=='content_block_start':blocks[event['index']]=dict(event['content_block'])
        elif kind=='content_block_delta':
            delta=event.get('delta',{})
            if delta.get('type')=='text_delta':
                block=blocks.setdefault(event['index'],{'type':'text','text':''})
                block['text']=block.get('text','')+delta.get('text','')
        elif kind=='message_delta':
            result.update(event.get('delta',{}));result.setdefault('usage',{}).update(event.get('usage',{}))
        elif kind=='error':return {'type':'error','error':event.get('error',{})}
        elif kind=='message_stop':break
    # Thinking contents are not needed for this disabled-thinking benchmark protocol.
    result['content']=[({'type':'text','text':b.get('text','')} if b.get('type')=='text' else {'type':b.get('type')}) for _,b in sorted(blocks.items())]
    return result

class Relay:
    def __init__(self,log_path):
        self.config=env_config();self.log_path=log_path;self.calls=[];self.session=requests.Session()
        base=self.config['ANTHROPIC_BASE_URL'].rstrip('/')
        self.endpoint=base if base.endswith('/messages') else base+('/messages' if base.endswith('/v1') else '/v1/messages')

    def complete(self,messages,label,max_tokens=2048):
        system='\n'.join(x['content'] for x in messages if x['role']=='system')
        body={'model':self.config['ANTHROPIC_MODEL'],'max_tokens':max_tokens,'temperature':0,
              'thinking':{'type':'disabled'},'output_config':{'effort':'low'},
              'stream':True,
              'messages':[x for x in messages if x['role']!='system']}
        if system:body['system']=system
        headers={'x-api-key':self.config['ANTHROPIC_API_KEY'],'anthropic-version':'2023-06-01','content-type':'application/json'}
        record={'label':label,'requested_model':body['model'],'messages':[dict(x) for x in messages],
                'request_settings':{'temperature':0,'max_tokens':max_tokens,'thinking':'disabled','effort':'low'},'attempts':[]}
        for attempt in range(3):
            start=time.monotonic()
            try:
                response=self.session.post(self.endpoint,headers=headers,json=body,timeout=(20,180),stream=True)
                record['attempts'].append({'attempt':attempt+1,'status':response.status_code,'seconds':round(time.monotonic()-start,3)})
                if response.status_code!=200:
                    if response.status_code in (408,429,500,502,503,504,529) and attempt<2:
                        time.sleep(2**attempt*2);continue
                    raise RelayError('HTTP_'+str(response.status_code))
                try:
                    result=decode_sse(response.iter_lines()) if 'text/event-stream' in response.headers.get('content-type','') else response.json()
                finally:response.close()
                record['attempts'][-1].update(usage=result.get('usage',{}),stop_reason=result.get('stop_reason'),
                    response_model=result.get('model'),content_types=[x.get('type') for x in result.get('content',[])])
                output='\n'.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')
                if result.get('stop_reason')=='refusal':
                    record.update(response_model=result.get('model'),stop_reason='refusal',usage=result.get('usage',{}),output=output)
                    self.calls.append(record);dump(self.log_path,self.calls)
                    return ''
                if not output:
                    err=result.get('error',{})
                    detail=json.dumps(err,ensure_ascii=False)
                    for value in self.config.values():
                        if value:detail=detail.replace(value,'[redacted]')
                    record['attempts'][-1]['response_shape']={'keys':list(result),'type':result.get('type'),
                        'content_types':[x.get('type') for x in result.get('content',[])],
                        'stop_reason':result.get('stop_reason'),'usage':result.get('usage',{}),
                        'error':detail[:350]}
                    dump(self.log_path,self.calls+[record])
                    if attempt<2:time.sleep(5*(attempt+1));continue
                    raise RelayError('NO_TEXT_BLOCK')
                record.update(response_model=result.get('model'),stop_reason=result.get('stop_reason'),usage=result.get('usage',{}),output=output)
                self.calls.append(record);dump(self.log_path,self.calls)
                if result.get('stop_reason')=='max_tokens':raise RelayError('OUTPUT_TRUNCATED')
                return output
            except requests.RequestException as e:
                record['attempts'].append({'attempt':attempt+1,'error_type':type(e).__name__,'seconds':round(time.monotonic()-start,3)})
                if attempt<2:time.sleep(2**attempt*2);continue
                record['error']='TRANSPORT_ERROR';self.calls.append(record);dump(self.log_path,self.calls)
                raise RelayError('TRANSPORT_ERROR') from None
            except (RelayError,ValueError) as e:
                record['error']=str(e) if isinstance(e,RelayError) else 'INVALID_JSON'
                if not self.calls or self.calls[-1] is not record:self.calls.append(record)
                dump(self.log_path,self.calls)
                raise RelayError(record['error']) from None
        raise RelayError('RETRY_EXHAUSTED')

def canonical(smiles):
    mol=Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol,isomericSmiles=True) if mol is not None else None

def prepare():
    prepared=ROOT/'prepared';prepared.mkdir(exist_ok=True)
    source_path=ROOT/'data/ChatDrug_data/small_molecule/small_molecule_editing.txt'
    source=list(dict.fromkeys(source_path.read_text().splitlines()))
    source_sample=random.Random(SEED).sample(source,20)
    cases=[]
    for task in (101,102,103,104):
        prop='LogP' if task<103 else 'QED';direction='lower' if task in (101,104) else 'higher'
        for i,smiles in enumerate(source_sample):
            cases.append({'id':f'source_{task}_{i:03d}','benchmark':'ChatDrug','task':task,'property':prop,'direction':direction,
                          'smiles':smiles,'instruction':SM.task_specification_dict_molecule[task].replace('SMILES_PLACEHOLDER',smiles),
                          'constraint':'loose'})
    excluded={canonical(s) for s in source}
    target_stats={}
    for prop in ('LogP','QED'):
        path=ROOT/'data/S2-TOMG-Bench-mini'/f'MolOpt_{prop}.csv'
        rows=list(csv.DictReader(path.open()))
        excluded.update(canonical(row['molecule']) for row in rows)
        selected=[]
        for direction in ('higher','lower'):
            pool=[(i,row) for i,row in enumerate(rows) if ('lower' if ('lower' in row['Instruction'] or 'decrease' in row['Instruction']) else 'higher')==direction]
            selected.extend(random.Random(SEED+(1 if direction=='lower' else 0)).sample(pool,10))
        selected.sort(key=lambda x:x[0])
        for rowidx,row in selected:
            direction='lower' if ('lower' in row['Instruction'] or 'decrease' in row['Instruction']) else 'higher'
            task=({'higher':102,'lower':101} if prop=='LogP' else {'higher':103,'lower':104})[direction]
            cases.append({'id':f's2_{prop}_{row["index"]}','benchmark':'S2-mini','task':task,'property':prop,'direction':direction,
                          'smiles':row['molecule'],'instruction':row['Instruction'],'constraint':'loose',
                          'original_row':rowidx,'original_index':row['index']})
        target_stats[prop]={'sha256':sha(path),'rows':len(rows),'pilot_rows':len(selected)}
    excluded.discard(None)
    db_path=ROOT/'data/ChatDrug_data/small_molecule/250k_rndm_zinc_drugs_clean_3.csv'
    corpus=pd.read_csv(db_path)
    emit({'prepare':'canonicalize_corpus','rows':len(corpus)})
    clean=[];seen=set();invalid=removed=duplicates=0
    for i,smiles in enumerate(corpus['smiles']):
        smiles=smiles.strip();can=canonical(smiles)
        if can is None:invalid+=1;continue
        if can in excluded:removed+=1;continue
        if can in seen:duplicates+=1;continue
        seen.add(can);clean.append(smiles)
        if i and i%50000==0:emit({'prepare_rows':i})
    db=pd.DataFrame({'sequence':clean}).sample(n=10000,random_state=0).reset_index(drop=True)
    db.to_csv(prepared/'retrieval.csv',index=False)
    dump(prepared/'cases.json',cases)
    manifest={'seed':SEED,'model':env_config()['ANTHROPIC_MODEL'],'temperature':0,'feedback_rounds':2,
              'source_cases':80,'target_cases':40,'target_data':target_stats,'source_input_sha256':sha(source_path),
              'corpus_sha256':sha(db_path),'corpus_rows':len(corpus),'excluded_unique_structures':len(excluded),
              'removed_test_overlap_rows':removed,'invalid_corpus_rows':invalid,'duplicate_canonical_rows':duplicates,
              'retrieval_rows':len(db),'retrieval_sha256':sha(prepared/'retrieval.csv'),
              'canonical_retrieval_test_overlap':sum(canonical(x) in excluded for x in db['sequence']),
              'rdkit_version':rdkit.__version__,'numpy_version':np.__version__,'pandas_version':pd.__version__,
              'upstream_source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [CD/'main_ChatDrug.py',CD/'utils.py',
                  CD/'ChatDrug/task_and_evaluation/small_molecule_editing.py',S2/'evaluate.py',S2/'utils/evaluation.py']},
              'protocol_notes':['First LLM response shared across arms for paired comparison.',
              'Upstream conversation/ReDF/parse retained; invalid cases remain in denominator.',
              'No target training or hyperparameter selection.',
              'Independent3 repeats deterministic-temperature requests; not a diverse-temperature search.',
              'Full mini LogP/QED inputs and all original 200 inputs excluded from fixed retrieval corpus.']}
    dump(prepared/'manifest.json',manifest);emit(manifest)

@functools.lru_cache(maxsize=15000)
def fingerprint(s):return AllChem.GetMorganFingerprint(Chem.MolFromSmiles(s),2)

@functools.lru_cache(maxsize=45000)
def prop_value(s,prop,kekulize=False):
    mol=Chem.MolFromSmiles(s)
    if kekulize:Chem.Kekulize(mol)
    return Descriptors.MolLogP(mol) if prop=='LogP' else Descriptors.qed(mol)

def score(case,candidate):
    if not candidate or Chem.MolFromSmiles(candidate) is None:
        return {'valid':False,'success':False,'similarity':None,'delta':None,'candidate':candidate}
    if case['benchmark']=='ChatDrug':
        original,modified,answer=SM.evaluate_molecule(case['smiles'],candidate,case['task'],[0])
        success=bool(answer==True)
    else:
        name='logP' if case['property']=='LogP' else 'qed'
        original=S2_PROP(case['smiles'],name);modified=S2_PROP(candidate,name)
        success=modified<original if case['direction']=='lower' else modified>original
    return {'valid':True,'success':success,'similarity':float(S2_SIM(case['smiles'],candidate)),
            'delta':float((modified-original)*(1 if case['direction']=='higher' else -1)),
            'candidate':candidate,'input_property':float(original),'output_property':float(modified)}

def parse_candidate(smiles,text,retrieval=None):
    candidates=SM.parse_molecule(smiles,text,retrieval)
    return candidates[0] if candidates else None

def run_case(case,db,outdir):
    start=time.monotonic();case_dir=outdir/case['id'];case_dir.mkdir(parents=True,exist_ok=True)
    if (case_dir/'result.json').exists():
        prev=json.loads((case_dir/'result.json').read_text())
        if prev.get('status')=='complete':return prev
    relay=Relay(case_dir/'api_calls.json')
    prompt=case['instruction']+' Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.'
    initial_messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':prompt}]
    result={'id':case['id'],'case':case,'status':'running','arms':{}}
    counter={'retrieval_property_evaluations':0,'retrieval_similarity_comparisons':0,'online_evaluations':0}
    try:
        initial=relay.complete(initial_messages,'shared_initial')
        first=score(case,parse_candidate(case['smiles'],initial))
        result['arms']['direct']={**first,'llm_calls_attributed':1}
        # Extract upstream functions verbatim, without importing unrelated peptide/protein stacks.
        first_pending=[True]
        def complete(messages,model,tokenizer,conversational_LLM,drug_type,round_index=None):
            if first_pending[0]:first_pending[0]=False;return initial
            return relay.complete(messages,f'chatdrug_feedback_{round_index}')
        def evaluate(input_drug,generated_drug,task,constraint,threshold_dict):
            counter['online_evaluations']+=1
            r=score(case,generated_drug)
            return bool(r['success']) if r['valid'] else -1
        def sim_sequence(task,a,b):
            counter['retrieval_similarity_comparisons']+=1
            return DataStructs.TanimotoSimilarity(fingerprint(a),fingerprint(b))
        # Same task-specific property direction as the upstream loose evaluator; memoized scalar calculation.
        def retrieval_evaluate(input_drug,generated_drug,task,constraint,threshold_dict):
            counter['retrieval_property_evaluations']+=1
            kekulize=case['benchmark']=='ChatDrug'
            iv=prop_value(input_drug,case['property'],kekulize);ov=prop_value(generated_drug,case['property'],kekulize)
            return ov<iv if case['direction']=='lower' else ov>iv
        rn=load_functions(CD/'utils.py',['retrieve_and_feedback'],{'sim_sequence':sim_sequence,'evaluate':retrieval_evaluate})
        namespace={'sys':sys,'complete':complete,'parse':lambda task,inp,text,other:SM.parse_molecule(inp,text,other),
                   'evaluate':evaluate,'retrieve_and_feedback':rn['retrieve_and_feedback']}
        load_functions(CD/'main_ChatDrug.py',['conversation','ReDF'],namespace)
        record={case['smiles']:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
        messages=[dict(m) for m in initial_messages];candidate=None;answer=0;rounds=0
        with (case_dir/'chatdrug.log').open('w') as logfile:
            for round_index in range(3):
                rounds+=1
                answer,candidate=namespace['conversation'](messages,None,None,'chatgpt',2,round_index,0,case['task'],
                    'molecule',case['smiles'],db,record,logfile,False,'loose',{},None,None)
                if answer!=0 or candidate is None:break
        dump(case_dir/'chatdrug_trace.json',record)
        # Preserve the last actual generated SMILES, including invalid output for honest scoring.
        last_generated=None
        for turn in record[case['smiles']]['retrieval_conversation']:
            if 'generated_drug' in turn:last_generated=turn['generated_drug']
        result['arms']['chatdrug']={**score(case,last_generated),'llm_calls_attributed':rounds,
            'upstream_answer':int(answer),'upstream_skipped':answer==-1,**counter}
        independent=[first]
        for i in (() if relay.calls[0].get('stop_reason')=='refusal' else (1,2)):
            text=relay.complete(initial_messages,f'independent_{i+1}')
            independent.append(score(case,parse_candidate(case['smiles'],text)))
            if relay.calls[-1].get('stop_reason')=='refusal':break
        best=max(independent,key=lambda x:(x['success'],x['valid'],x['similarity'] if x['similarity'] is not None else -1,x['delta'] if x['delta'] is not None else -1e9))
        result['arms']['independent3']={**best,'llm_calls_attributed':len(independent),'candidates':independent}
        result['status']='complete'
    except Exception as e:
        result['status']='error';result['error_type']=type(e).__name__
        result['error']=str(e) if isinstance(e,RelayError) else 'See sanitized stage diagnostics'
    result['seconds']=round(time.monotonic()-start,3)
    result['api_requests']=sum(len(c.get('attempts',[])) for c in relay.calls)
    result['logical_llm_calls']=len(relay.calls)
    result['retry_attempts']=sum(max(0,len(c.get('attempts',[]))-1) for c in relay.calls)
    result['usage']={k:sum(a.get('usage',{}).get(k,0) or 0 for c in relay.calls for a in c.get('attempts',[])) for k in ['input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens']}
    result['response_models']=sorted({c['response_model'] for c in relay.calls if c.get('response_model')})
    result['truncated_responses']=sum(c.get('stop_reason')=='max_tokens' for c in relay.calls)
    result['refusals']=sum(c.get('stop_reason')=='refusal' for c in relay.calls)
    dump(case_dir/'result.json',result)
    emit({'case':case['id'],'status':result['status'],'success':{k:v['success'] for k,v in result['arms'].items()},'seconds':result['seconds']})
    return result

def official_target_check(results,arm,prop):
    subset=[r for r in results if r['case']['benchmark']=='S2-mini' and r['case']['property']==prop and arm in r['arms']]
    if not subset:return None
    data=[{'molecule':r['case']['smiles'],'Instruction':r['case']['instruction']} for r in subset]
    target=pd.DataFrame({'outputs':[r['arms'][arm]['candidate'] or 'INVALID' for r in subset]})
    tree=ast.parse((S2/'evaluate.py').read_text())
    block=next(n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and ast.unparse(n.test)=="args.benchmark == 'open_generation'")
    ns={'args':SimpleNamespace(benchmark='open_generation',task='MolOpt',subtask=prop,calc_novelty=False),
        'data':data,'data_len':len(data),'target':target,'mol_prop':S2_PROP,'calculate_similarity':S2_SIM,'tqdm':lambda x:x}
    output=io.StringIO()
    try:
        with contextlib.redirect_stdout(output):exec(compile(ast.Module(body=[block],type_ignores=[]),str(S2/'evaluate.py'),'exec'),ns)
    except ZeroDivisionError:
        return {'upstream_all_invalid_division_by_zero':True,'validity':0,'success_rate':0,'similarity':None}
    checks={'stdout':output.getvalue(),'success_rate':sum(ns['successed'])/len(ns['successed']),
            'validity':len(ns['valid_molecules'])/len(data),'similarity':sum(ns['similarities'])/len(ns['similarities'])}
    assert abs(checks['success_rate']-sum(r['arms'][arm]['success'] for r in subset)/len(subset))<1e-12
    return checks

def summarize(stage):
    outdir=ROOT/'runs'/stage
    results=[json.loads(p.read_text()) for p in sorted(outdir.glob('*/result.json'))]
    complete=[r for r in results if r['status']=='complete']
    groups=[]
    for bench in ('ChatDrug','S2-mini'):
        for prop in ('LogP','QED'):
            rows=[r for r in complete if r['case']['benchmark']==bench and r['case']['property']==prop]
            for arm in ('direct','chatdrug','independent3'):
                vals=[r['arms'][arm] for r in rows]
                if not vals:continue
                valid=[v for v in vals if v['valid']]
                groups.append({'benchmark':bench,'property':prop,'arm':arm,'n':len(vals),
                    'successes':sum(v['success'] for v in vals),'success_rate':sum(v['success'] for v in vals)/len(vals),
                    'validity':len(valid)/len(vals),'similarity_valid':sum(v['similarity'] for v in valid)/len(valid) if valid else None,
                    'mean_calls_attributed':sum(v['llm_calls_attributed'] for v in vals)/len(vals)})
    official={f'{arm}_{prop}':official_target_check(complete,arm,prop) for arm in ('direct','chatdrug','independent3') for prop in ('LogP','QED')}
    summary={'stage':stage,'completed_cases':len(complete),'errored_cases':len(results)-len(complete),'groups':groups,
             'api_requests':sum(r['api_requests'] for r in results),'retry_attempts':sum(r['retry_attempts'] for r in results),
             'truncated_responses':sum(r['truncated_responses'] for r in results),
             'usage':{k:sum(r['usage'].get(k,0) for r in results) for k in ['input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens']},
             'official_target_crosscheck':official,'response_models':sorted({m for r in results for m in r['response_models']}),
             'chatdrug_feedback_cases':sum(r['arms'].get('chatdrug',{}).get('llm_calls_attributed',0)>1 for r in results),
             'invalid_direct_cases':sum(not r['arms'].get('direct',{}).get('valid',False) for r in results),
             'errors':[{'id':r['id'],'error':r.get('error'),'type':r.get('error_type')} for r in results if r['status']!='complete']}
    dump(outdir/'summary.json',summary)
    if groups:
        with (outdir/'metrics.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(groups[0]));writer.writeheader();writer.writerows(groups)
    emit(summary)
    return summary

def validate():
    cases=json.loads((ROOT/'prepared/cases.json').read_text())
    db=pd.read_csv(ROOT/'prepared/retrieval.csv')
    checked=0
    for task in (101,102,103,104):
        case=next(c for c in cases if c['task']==task)
        for s in db['sequence'].head(25):
            direct=SM.evaluate_molecule(case['smiles'],s,task,[0])[2]
            iv=prop_value(case['smiles'],case['property'],True);ov=prop_value(s,case['property'],True)
            cached=ov<iv if case['direction']=='lower' else ov>iv
            assert bool(direct)==cached;checked+=1
    manifest=json.loads((ROOT/'prepared/manifest.json').read_text())
    assert manifest['canonical_retrieval_test_overlap']==0
    assert len(cases)==120 and len({c['id'] for c in cases})==120
    assert len(db)==10000
    for prop in ('LogP','QED'):
        target=[c for c in cases if c['benchmark']=='S2-mini' and c['property']==prop]
        assert collections.Counter(c['direction'] for c in target)=={'higher':10,'lower':10}
    dump(ROOT/'prepared/validation.json',{'passed':True,'upstream_scalar_equivalence_checks':checked,'cases':120,'retrieval_rows':10000,'canonical_overlap':0})
    emit({'validation':'passed','scalar_checks':checked})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['probe','prepare','validate','run','summary'])
    parser.add_argument('--stage',default='smoke');parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    if args.action=='probe':
        relay=Relay(ROOT/'runs/probe_calls.json')
        output=relay.complete([{'role':'user','content':'Reply with exactly OK.'}],'connectivity',max_tokens=64)
        emit({'probe':'ok','text':output,'requested_model':relay.config['ANTHROPIC_MODEL'],'response_model':relay.calls[-1].get('response_model'),'usage':relay.calls[-1].get('usage')})
    elif args.action=='prepare':prepare()
    elif args.action=='validate':validate()
    elif args.action=='summary':summarize(args.stage)
    else:
        cases=json.loads((ROOT/'prepared/cases.json').read_text());db=pd.read_csv(ROOT/'prepared/retrieval.csv')
        if args.stage=='smoke':
            cases=[next(c for c in cases if c['benchmark']==bench and c['property']==prop and c['direction']==direction)
                   for bench,prop,direction in [('ChatDrug','LogP','lower'),('ChatDrug','QED','higher'),('S2-mini','LogP','higher'),('S2-mini','QED','lower')]]
        elif args.stage=='stream_check':
            # New fixed cases, not retrying items whose earlier response was a refusal.
            cases=[next(c for c in cases if c['id']=='source_103_001'),
                   next(c for c in cases if c['benchmark']=='S2-mini' and c['property']=='QED' and c['direction']=='higher')]
        elif args.stage!='pilot':raise ValueError('Unknown stage')
        outdir=ROOT/'runs'/args.stage;outdir.mkdir(exist_ok=True,parents=True)
        dump(outdir/'run_config.json',{'model':env_config()['ANTHROPIC_MODEL'],'thinking':'disabled','effort':'low',
            'temperature':0,'max_output_tokens':2048,'workers':args.workers,'case_ids':[c['id'] for c in cases],
            'runner_sha256':sha(__file__),'manifest_sha256':sha(ROOT/'prepared/manifest.json'),
            'retry_policy':'max 3 attempts per logical request; 2 case errors halt scheduling'})
        emit({'start':args.stage,'cases':len(cases),'workers':args.workers,'model':env_config()['ANTHROPIC_MODEL']})
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(run_case,c,db,outdir) for c in cases]
            errors=0
            for f in concurrent.futures.as_completed(futures):
                res=f.result()
                if res['status']=='error':
                    errors+=1
                    if errors>=2:
                        for waiting in futures:waiting.cancel()
                        emit({'halt':'two_case_errors'});break
        summary=summarize(args.stage)
        if summary['errored_cases'] or summary['completed_cases']!=len(cases):sys.exit(2)

if __name__=='__main__':main()
