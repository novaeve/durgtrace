"""No task-rule checker, no gold access, no invented model stopping decision."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import argparse,concurrent.futures,fcntl,io,json,re,sys,time,types,traceback
from rdkit import Chem,RDLogger
from transport import Relay,LongTruncation,dump,sha,functions
RDLogger.DisableLog('rdApp.*')
ROOT=Path(__file__).resolve().parent
VARIANT='validity_only_no_task_rules_v2'

def public_prompt(case,method):
    phrase='Return the resulting SMILES string enclosed within <smiles> and </smiles> tags.'
    assert case['prompt'].count(phrase)==1
    requirement=('Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.' if method=='chatdrug' else 'Respond with only the SMILES string of your molecule. No explanation is needed.')
    return case['prompt'].replace(phrase,requirement)

def chatdrug(case,relay,out):
    selected=[];calls=0;validity=[];retrieval_attempts=0
    parser=functions(ROOT/'agent_source/chatdrug_parser.py',['parse_molecule'],{'re':re})['parse_molecule']
    def complete(messages,*args):
        nonlocal calls
        calls+=1
        return relay.complete(messages,f'chatdrug/{calls}')
    def parse(task,inp,raw,ref):
        values=parser(inp,raw,ref)
        selected.append(values[0] if values else None)
        return values
    def evaluate(inp,sm,*args):
        valid=Chem.MolFromSmiles(sm) is not None
        validity.append(valid)
        # None is unknown, not a chemical/task success or a verified failure.
        return None if valid else -1
    def retrieval(*args):
        nonlocal retrieval_attempts
        retrieval_attempts+=1
        # Original ReDF requires a verified correct reference. No task oracle is
        # available, so use its native unavailable-reference exit, not a random
        # or unverified reference falsely labelled correct.
        raise Exception('Task verifier unavailable; cannot certify a reference')
    ns={'sys':sys,'complete':complete,'parse':parse,'evaluate':evaluate,'retrieve_and_feedback':retrieval}
    functions(ROOT/'agent_source/chatdrug_main.py',['conversation','ReDF'],ns)
    parent=case.get('original_smiles')
    record={parent:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
    messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':public_prompt(case,'chatdrug')}]
    log=io.StringIO()
    for round_index in range(3):
        answer,candidate=ns['conversation'](messages,None,None,'chatgpt',2,round_index,0,101,'molecule',parent,None,record,log,False,None,{},None,None)
        if answer!=0 or candidate is None:
            break
    state={'generation_calls':calls,'max_generations':3,'native_answer':answer,'validity':validity,'retrieval_attempts':retrieval_attempts,'task_status':'not_evaluated','stop_reason':'reference_verifier_unavailable' if retrieval_attempts else 'native_parse_or_validity_exit','feedback_scope':'validity_only','autonomous_submit_added':False}
    dump(out/'trace.json',{'state':state,'messages':messages,'record':record,'native_log':log.getvalue()})
    return selected[-1] if selected else None,state

def agentdrug(case,relay,out):
    predictions=[];validity=[]
    def validity_feedback(sm,_):
        valid=Chem.MolFromSmiles(sm) is not None
        validity.append(valid)
        return 'The modified molecule is chemically valid.' if valid else 'The modified molecule is not chemically valid.'
    ns={'get_validity_feedback':validity_feedback,'listize_fn':lambda batch:{k:[v] for k,v in batch.items()}}
    exec(compile((ROOT/'agent_source/agentdrug_validity_only.py').read_text(),'<agentdrug_validity_only>','exec'),ns)
    class Model:
        def inference(self,batch):
            value=relay.complete([{'role':'user','content':batch['prompt'][0]}],f'agentdrug/{len(predictions)+1}',cap=256).strip()
            predictions.append(value)
            return {'id':batch['id'],'label':batch['smiles'],'pred':[value]}
    maximum=4 if case['task']=='edit' else 5
    args=types.SimpleNamespace(data='validity_only/'+case['task'],refine_steps=maximum-1)
    batch={'id':case['id'],'smiles':case.get('original_smiles'),'prompt':public_prompt(case,'agentdrug')+'\nAnswer:','label':None}
    outputs,invalid,steps=ns['run_core'](args,batch,Model(),None)
    assert len(outputs)==1
    state={'generation_calls':len(predictions),'max_generations':maximum,'validity_feedback_count':invalid,'core_iterations':steps,'task_status':'not_evaluated','stop_reason':'native_round_limit','feedback_scope':'validity_only','autonomous_submit_added':False}
    dump(out/'trace.json',{'state':state,'predictions':predictions,'validity':validity,'outputs':outputs})
    return outputs[0]['pred'][0],state

def job(method,case,stage):
    out=ROOT/'runs'/stage/method/case['id'];out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
    start=time.time();relay=Relay(out)
    row={'method':method,'variant':VARIANT,'id':case['id'],'task':case['task'],'split':case['split'],'index':case['index'],'started':start}
    try:
        candidate,details=globals()[method](case,relay,out)
        row.update(status='complete',candidate=candidate,output='<smiles>'+(candidate or '')+'</smiles>',details=details)
    except LongTruncation:
        row.update(status='error',error='PROVIDER_OUTPUT_TRUNCATED',candidate=None,output='')
    except Exception as e:
        row.update(status='error',error=type(e).__name__,candidate=None,output='')
        (out/'error.txt').write_text(traceback.format_exc())
    row.update(ended=time.time(),seconds=time.time()-start,usage=relay.usage())
    dump(out/'result.json',row)
    print(json.dumps({'method':method,'id':case['id'],'status':row['status'],'calls':row['usage']['llm_calls'],'error':row.get('error')}),flush=True)
    return row

def deny_gold(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        name=os.fsdecode(args[0]).replace('\\','/').lower()
        if name.endswith('/answers.json') or name.endswith('.parquet'):
            raise PermissionError('Gold/dataframe access forbidden during inference')

def main():
    sys.addaudithook(deny_gold)
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);ap.add_argument('method',choices=['chatdrug','agentdrug']);a=ap.parse_args()
    folder=ROOT/'runs'/a.stage/a.method;folder.mkdir(parents=True,exist_ok=True)
    lock=(folder/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cases=json.loads((ROOT/'data/cases.json').read_text())
    if a.stage=='pilot':cases=[c for c in cases if c['index']<2]
    else:
        pilot=[json.loads(p.read_text()) for p in (ROOT/'runs/pilot'/a.method).glob('*/result.json')]
        assert len(pilot)==8 and all(r['status']=='complete' or r.get('error')=='PROVIDER_OUTPUT_TRUNCATED' for r in pilot)
    config={'method':a.method,'variant':VARIANT,'model':'deepseek-v4.1-flash','temperature':0,'thinking':False,'gold_access':False,'workers':4,'expected':len(cases),'manifest_sha256':sha(ROOT/'data/experiment_manifest.json'),'cases_sha256':sha(ROOT/'data/cases.json'),'task_rule_checker':False,'verified_reference_available':False,'agentdrug_round_mapping':'existing adaptation: edit 4, generation 5','code_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'run_agents.py',ROOT/'transport.py',ROOT/'agent_source/agentdrug_validity_only.py',ROOT/'agent_source/chatdrug_main.py',ROOT/'agent_source/chatdrug_parser.py']}}
    cp=folder/'config.json'
    if cp.exists():assert json.loads(cp.read_text())==config
    else:dump(cp,config)
    rows={r['id']:r for p in folder.glob('*/result.json') for r in [json.loads(p.read_text())]}
    pending=[c for c in cases if c['id'] not in rows];pending.sort(key=lambda c:(c['index'],c['task'],c['split']))
    def summary():
        d={'processed':len(rows),'expected':len(cases),'runtime_errors':sum(r['status']!='complete' for r in rows.values()),'updated':time.time(),'variant':VARIANT}
        dump(folder/'summary.json',d);return d
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        fs=[pool.submit(job,a.method,c,a.stage) for c in pending]
        for f in concurrent.futures.as_completed(fs):
            r=f.result();rows[r['id']]=r;summary()
    print(json.dumps(summary()),flush=True)
if __name__=='__main__':main()
