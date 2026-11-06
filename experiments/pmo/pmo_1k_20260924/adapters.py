"""Existing agent cores with PMO scalar evaluation and a budgeted retrieval archive."""
import ast, importlib.util, io, pathlib, re, sys, types
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem
from pmo_common import ROOT, functions, canonical, dump, BudgetExhausted
from task_specs import instruction
CHAT = pathlib.Path('/data2/chenfuxin/chatdrug_generalization_20260920/upstream/ChatDrug')
AGENT = pathlib.Path('/data2/chenfuxin/agentdrug_20260922')
MOL = pathlib.Path('/data2/chenfuxin/molingo_20260922')

def fp(sm): return AllChem.GetMorganFingerprint(Chem.MolFromSmiles(sm),2)

def context(task, ledger):
    previous=ledger.rows[:ledger.episode_boundary][-20:]
    return instruction(task)+'\nPreviously evaluated structures (repeating them yields no new oracle information):\n'+'\n'.join(r['smiles'] for r in previous)

def archive(ledger):
    return {r['smiles']:[r['score'],r['index']] for r in ledger.rows[:ledger.episode_boundary]}

def initial(task, parent, ledger):
    return context(task,ledger)+'\nImprove the following starting molecule for this objective: '+parent

def direct(task,parent,ledger,relay,label,out):
    prompt=initial(task,parent,ledger)+'\nReturn only one candidate SMILES, without explanation.'
    text=relay.complete([{'role':'user','content':prompt}],label+'/direct')
    clean=text.strip().strip('`').strip()
    if clean.startswith('smiles\n'):clean=clean[7:].strip()
    ledger.score(clean,'generated/direct')
    return {'raw':text,'candidates':[clean]}

def chatdrug(task,parent,ledger,relay,label,out):
    parser=functions(CHAT/'ChatDrug/task_and_evaluation/small_molecule_editing.py',['parse_molecule'],{'re':re})['parse_molecule']
    base=ledger.score(parent,'parent_cached')
    # Retrieve only already evaluated molecules. Snapshot is frozen within an episode.
    db=pd.DataFrame({'sequence':list(archive(ledger))})
    def evaluate(inp, candidate, *a, **kw):
        if canonical(candidate) is None:ledger.score(candidate,'generated/chatdrug');return -1
        return ledger.score(candidate,'generated/chatdrug') > base
    def retrieval_evaluate(inp,candidate,*a,**kw):
        return ledger.score(candidate,'retrieval_cached/chatdrug') > base
    retrieval=functions(CHAT/'utils.py',['retrieve_and_feedback'],
        {'sim_sequence':lambda t,a,b:DataStructs.TanimotoSimilarity(fp(a),fp(b)), 'evaluate':retrieval_evaluate})
    ns={'sys':sys,'complete':lambda messages,*a:relay.complete(messages,label+f'/chatdrug/{len(messages)}'),
        'parse':lambda t,i,text,other:parser(i,text,other),'evaluate':evaluate,
        'retrieve_and_feedback':retrieval['retrieve_and_feedback']}
    functions(CHAT/'main_ChatDrug.py',['conversation','ReDF'],ns)
    record={parent:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
    messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},
        {'role':'user','content':initial(task,parent,ledger)+' Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.'}]
    log=io.StringIO()
    for i in range(3):
        if len(ledger.buffer)>=ledger.budget:break
        answer,candidate=ns['conversation'](messages,None,None,'chatgpt',2,i,0,101,'molecule',parent,db,record,log,False,'loose',{},None,None)
        if answer!=0 or candidate is None:break
    return {'trace':record,'log':log.getvalue()}

def agentdrug(task,parent,ledger,relay,label,out):
    # Add one generic scalar branch to the previous source-derived core; no remapping to QED.
    code=(AGENT/'core_fixed.py').read_text()
    anchor='                        if prop == "LogP+":'
    assert code.count(anchor)==1
    code=code.replace(anchor,'''                        if prop == "PMO+":
                            hit = output_prop > input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop]
                            property_feedback = f"The modified molecule has a PMO objective score of {output_prop:.6f} and the original one has {input_prop:.6f}. A higher score is desired."
'''+anchor)
    ns={'Chem':Chem,'AllChem':AllChem,'DataStructs':DataStructs,
        'task2func':{'PMO+':lambda mol:ledger.score(Chem.MolToSmiles(mol),'feedback/agentdrug')},
        'task2thres':{'PMO+':[[0],[0]]},
        'get_validity_feedback':lambda sm,_:'The modified molecule is chemically valid.' if canonical(sm) else 'The modified molecule is not chemically valid.',
        'listize_fn':lambda batch:{k:[v] for k,v in batch.items()}}
    exec(compile(code,'agentdrug_pmo_core','exec'),ns)
    db=pd.DataFrame([{'SMILES':sm,'mol':Chem.MolFromSmiles(sm),'prop':v[0]} for sm,v in archive(ledger).items()])
    class Model:
        def __init__(self):self.n=0;self.outputs=[]
        def inference(self,batch):
            if len(ledger.buffer)>=ledger.budget:raise BudgetExhausted()
            self.n+=1
            text=relay.complete([{'role':'user','content':batch['prompt'][0]}],label+f'/agentdrug/{self.n}',cap=256)
            cleaned=text.strip().split('->',1)[-1].split('becomes',1)[-1].strip()
            # The final iteration has no internal evaluation in upstream; PMO records it too.
            ledger.score(cleaned,'generated/agentdrug'); self.outputs.append(text)
            return {'id':batch['id'],'label':batch['smiles'],'pred':[text.strip()]}
    model=Model()
    batch={'id':label,'smiles':parent,'label':None,'prompt':initial(task,parent,ledger)+'\nRespond with only the SMILES string of your modified molecule. No explanation is needed.\n\nMolecule:'+parent+'\nAnswer:'}
    args=types.SimpleNamespace(data='single/PMO+',refine_steps=3,hit_thres=0)
    outputs,valid,total=ns['run_core'](args,batch,model,types.SimpleNamespace(DB=db))
    return {'outputs':outputs,'raw_outputs':model.outputs,'validity_feedback':valid,'iterations':total}

_mol=None
def molingo(task,parent,ledger,relay,label,out):
    global _mol
    if _mol is None:
        spec=importlib.util.spec_from_file_location('pmo_molingo_runner',MOL/'runner.py')
        _mol=importlib.util.module_from_spec(spec);spec.loader.exec_module(_mol)
        # Per-run cache avoids simultaneous JSON writes between independent processes.
        _mol.CACHE=out/'molingo_cache';_mol.CACHE.mkdir(exist_ok=True)
        _mol.STRUCTURES={};_mol.NAMES=dict(_mol.NAMES)
    ns=_mol.core_namespace(lambda prompt:relay.complete([{'role':'user','content':prompt}],label+'/molingo'))
    try:
        candidates=ns['optimize_mol_tomg'](parent,main_task=task,trend='increase',variants=3,task_instruction=context(task,ledger))
    except ValueError as e:
        if str(e)!='MODEL_MODIFICATION_LIST_UNPARSEABLE':raise
        return {'model_failure':str(e),'candidates':[]}
    # Original order, all candidates; neither filtering no-ops nor score-based reordering.
    dump(out/'pending_candidates.json',{'label':label,'candidates':candidates})
    for sm in candidates:
        if len(ledger.buffer)>=ledger.budget:break
        ledger.score(sm,'generated/molingo')
    return {'candidates':candidates}

METHODS={'deepseek':direct,'chatdrug':chatdrug,'agentdrug':agentdrug,'molingo':molingo}
