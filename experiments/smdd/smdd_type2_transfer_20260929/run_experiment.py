"""Three independent Type2 methods, public-only inference, offline scoring."""
from pathlib import Path
import os,sys,json,time,types,io,ast,argparse,hashlib,traceback
import yaml
from runtime import ROOT,API,dump,baseline
from csv_adapter import extract_csv,format_feedback
from agent_harness.obfuscate import obfuscate_task

def functions(path,names,ns):
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)

def prompt(task,public):
    return task['description']+'\n\nThe complete public input file receptor.pdb follows:\n<pdb>\n'+(public/'receptor.pdb').read_text()+'\n</pdb>\nReturn the contents of solution.csv: exactly three rows x,y,z,type, without a header. You may enclose the CSV in a code block.'

def chatdrug(task,public,out):
    api=API(out);selected=[];state={'task_correctness':'unknown','max_generations':3}
    def complete(messages,*args):return api.complete(messages)['choices'][0]['message']['content'] or ''
    def parse(*args):
        candidate=extract_csv(args[2]);selected.append(candidate)
        return [candidate] if candidate else []
    def evaluate(inp,sm,*args):return None if format_feedback(sm)[0] else -1
    def retrieval(*args):raise Exception('No reference library supports pharmacophore-point CSV verification')
    ns={'sys':sys,'complete':complete,'parse':parse,'evaluate':evaluate,'retrieve_and_feedback':retrieval}
    functions(ROOT/'agent_source/chatdrug_main.py',['conversation','ReDF'],ns)
    record={None:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
    messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':prompt(task,public)}]
    log=io.StringIO()
    for i in range(3):
        answer,candidate=ns['conversation'](messages,None,None,'chatgpt',2,i,0,101,'molecule',None,None,record,log,False,None,{},None,None)
        if answer!=0 or candidate is None:break
    pred=selected[-1] if selected else ''
    (out/'solution.csv').write_text(pred)
    state.update(calls=api.calls,format_valid=format_feedback(pred)[0],stop_reason='native_reference_unavailable' if format_feedback(pred)[0] else 'native_parse_or_validity_exit',tokens=api.total_tokens)
    dump(out/'trace.json',{'state':state,'messages':messages,'record':record,'log':log.getvalue()})
    return state

def agentdrug(task,public,out):
    api=API(out);preds=[]
    source=(ROOT/'agent_source/agentdrug_core.py').read_text()
    start=source.index('                    input_mol = Chem.MolFromSmiles')
    end=source.index('            except:\n                continue',start)
    source=source[:start]+'''                    feedback_output = "Validity:\\n{}\\nTask correctness is unknown; no verified pharmacophore reference is available.".format(validity_feedback)
'''+source[end:]
    source=source.replace('"not chemically valid"','"format is invalid"')
    source=source.replace('Respond with only the SMILES string of your modified molecule. No explanation is needed.','Return the contents of solution.csv: exactly three rows x,y,z,type, without a header. You may enclose the CSV in a code block.')
    source=source.replace('Improve the modified molecule','Revise the CSV solution')
    ns={'get_validity_feedback':lambda s,_:format_feedback(s)[1],'listize_fn':lambda b:{k:[v] for k,v in b.items()}}
    exec(compile(source,'<agentdrug_csv_format_only>','exec'),ns)
    class Model:
        def inference(self,b):
            data=api.complete([{'role':'user','content':b['prompt'][0]}],cap=256)
            value=extract_csv(data['choices'][0]['message']['content'] or '');preds.append(value)
            return {'id':b['id'],'label':b['smiles'],'pred':[value]}
    args=types.SimpleNamespace(data='type2/csv',refine_steps=3)
    batch={'id':task['id'],'smiles':None,'prompt':prompt(task,public),'label':None}
    outputs,invalid,steps=ns['run_core'](args,batch,Model(),None)
    assert len(outputs)==1
    pred=outputs[0]['pred'][0];(out/'solution.csv').write_text(pred)
    state={'calls':api.calls,'max_generations':4,'format_valid':format_feedback(pred)[0],'format_feedback_count':invalid,'task_correctness':'unknown','tokens':api.total_tokens}
    dump(out/'trace.json',{'state':state,'predictions':preds,'outputs':outputs})
    return state

def guard(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)) and os.fsdecode(args[0]).replace('\\','/').endswith('/ground_truth.json'):
        raise PermissionError('Ground truth forbidden during inference')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('method',choices=['deepseek','chatdrug','agentdrug']);ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
    sys.addaudithook(guard)
    ids=[s.strip() for s in (ROOT/'task_list.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    assert len(ids)==25
    if a.pilot:ids=ids[:1]
    else:
        r=json.loads((ROOT/'runs'/a.method/ids[0]/'result.json').read_text())
        assert r['status'] not in ['error','llm_error'], 'Pilot infrastructure failure; do not launch full batch'
    for index,tid in enumerate(ids):
        out=ROOT/'runs'/a.method/tid;out.mkdir(parents=True,exist_ok=True)
        if (out/'result.json').exists():continue
        task=yaml.safe_load((ROOT/'tasks'/tid/'task.yaml').read_text())
        public=Path(obfuscate_task(str(ROOT/'tasks'/tid),f'task_{index:03d}'))
        assert set(p.name for p in public.iterdir())=={'receptor.pdb'}
        start=time.time()
        try:
            details=baseline(task,public,out) if a.method=='deepseek' else globals()[a.method](task,public,out)
            result={'status':details.get('status','complete'),'details':details}
        except Exception as e:
            result={'status':'error','error':type(e).__name__}
            (out/'error.log').write_text(traceback.format_exc())
        result.update(method=a.method,task=tid,started=start,ended=time.time(),seconds=time.time()-start,public_pdb_sha256=hashlib.sha256((public/'receptor.pdb').read_bytes()).hexdigest())
        dump(out/'result.json',result)
        print(json.dumps(result),flush=True)
        if result['status'] in ['error','llm_error']:raise RuntimeError('Infrastructure/API failure; inspect before continuing')
if __name__=='__main__':main()
