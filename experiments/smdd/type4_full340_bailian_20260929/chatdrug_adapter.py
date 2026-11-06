"""Budgeted ChatDrug retrieval/domain feedback over unchanged SMDD initial prompts.

SMDD tools provide the candidate-generation interface. After a non-reference
candidate's ADMET assessment fails a public task condition, ReDF searches a
fixed external corpus in similarity order. All learned-oracle checks consume
the same executor budgets. No witness, historical answer, or evaluator output
is exposed to generation. Two retrieval-feedback rounds maximum.
"""
import ast,csv,json,pathlib,tempfile,time
from rdkit import Chem,DataStructs,RDLogger
from rdkit.Chem import AllChem,Descriptors,Crippen,Lipinski,RDConfig
from rdkit.Chem.FilterCatalog import FilterCatalog,FilterCatalogParams
import sys
sys.path.append(str(pathlib.Path(RDConfig.RDContribDir)/'SA_Score'))
import sascorer
from agent_harness.tools import ToolExecutor
from gpu_transport import predict

ROOT=pathlib.Path(__file__).resolve().parent
RDLogger.DisableLog('rdApp.*')

def hard_namespace():
    # Original hard-constraint function, copied from frozen SMDD source.
    ns=dict(Chem=Chem,Descriptors=Descriptors,Crippen=Crippen,Lipinski=Lipinski,AllChem=AllChem,
        DataStructs=DataStructs,sascorer=sascorer)
    for name,kind in (('_PAINS_CATALOG',FilterCatalogParams.FilterCatalogs.PAINS),('_BRENK_CATALOG',FilterCatalogParams.FilterCatalogs.BRENK)):
        params=FilterCatalogParams();params.AddCatalog(kind);ns[name]=FilterCatalog(params)
    tree=ast.parse((ROOT/'frozen_lead_optimization.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('read_smiles_file','assess_hard_constraints')]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'frozen_hard_constraints','exec'),ns)
    return ns

HARD=hard_namespace()['assess_hard_constraints']

class ChatDrugExecutor(ToolExecutor):
    def __init__(self,container_id,config,task,task_dir,output_dir):
        super().__init__(container_id,config)
        self.task=task;self.task_dir=pathlib.Path(task_dir);self.output_dir=pathlib.Path(output_dir)
        self.reference=next(iter(Chem.SDMolSupplier(str(self.task_dir/'reference.sdf'))))
        self.reference_smiles=Chem.MolToSmiles(self.reference,isomericSmiles=True)
        self.reference_fp=AllChem.GetMorganFingerprintAsBitVect(self.reference,2,nBits=2048)
        self.rounds=0;self.pending=None;self.seen=set();self.cache={};self.boltz_context=None;self.terminal_candidate=None
        self.audit=self.output_dir/'chatdrug_events.jsonl'
        # Same database rows as source run, excluding this task's exact input.
        self.pool=[]
        for row in csv.DictReader((ROOT/'retrieval.csv').open()):
            mol=Chem.MolFromSmiles(row['sequence'])
            if mol is None:continue
            if Chem.MolToSmiles(mol,isomericSmiles=True)==self.reference_smiles:continue
            self.pool.append((row['sequence'],AllChem.GetMorganFingerprint(mol,2)))
        self.event('retrieval_pool',{'rows':len(self.pool),'prefilter':'valid molecules, exact input excluded; no similarity cutoff'})

    def event(self,event,data):
        with self.audit.open('a') as f:f.write(json.dumps({'event':event,'time':time.time(),**data})+'\n')

    def hard(self,smiles,*,retrieval=False):
        with tempfile.NamedTemporaryFile(mode='w',suffix='.smi') as f:
            f.write(smiles);f.flush()
            return HARD(f.name,str(self.task_dir/'reference.sdf'),skip_tanimoto=retrieval)['all_passed']

    def admet_pass(self,values):
        for x in self.task['optimization_objectives']:
            prop=x['property']
            if prop=='binding_affinity':continue
            if prop not in values:return False
            delta=values[prop]-self.task['baseline_values'][prop]
            if (delta if x['direction']=='maximize' else -delta)<x['threshold']:return False
        for x in self.task['hold_constant']:
            prop=x['property']
            if prop=='binding_affinity':continue
            if prop not in values:return False
            delta=values[prop]-self.task['baseline_values'][prop]
            change=delta if x['direction']=='increase' else -delta if x['direction']=='decrease' else abs(delta)
            if change>x['tolerance']:return False
        return True

    def dispatch(self,name,args):
        result,extra=super().dispatch(name,args)
        if name=='predict_boltz' and args.get('protein_sequences'):
            self.boltz_context={k:v for k,v in args.items() if k not in ('smiles','reasoning')}
            try:
                r=json.loads(result);s=args['smiles'];m=Chem.MolFromSmiles(s)
                if m is not None and Chem.MolToSmiles(m,isomericSmiles=True)!=self.reference_smiles and s not in self.seen:
                    failed=r.get('binding_probability',1)<=0.7
                    if 'affinity_pred_value' in r:
                        av=r['affinity_pred_value'];bv=self.task['baseline_values']['binding_affinity']
                        failed=failed or any(bv-av<x['threshold'] for x in self.task['optimization_objectives'] if x['property']=='binding_affinity')
                        failed=failed or any(av-bv>x['tolerance'] for x in self.task['hold_constant'] if x['property']=='binding_affinity')
                    if failed:self.pending=s
            except (ValueError,TypeError):pass
        if name=='predict_admet' and args.get('smiles') and not extra.get('budget_exceeded'):
            try:
                values=json.loads(result);s=args['smiles'];m=Chem.MolFromSmiles(s)
                if m is not None and any(k in values for k in ('clearance','herg','ppb')):
                    self.cache[s]=values
                    if Chem.MolToSmiles(m,isomericSmiles=True)!=self.reference_smiles and s not in self.seen:
                        if not self.hard(s) or not self.admet_pass(values):self.pending=s
            except (ValueError,TypeError):pass
        return result,extra

    def run_predict_boltz(self,args):
        if self.boltz_calls>=self.config.boltz_budget:return 'ERROR: Boltz budget exceeded',{'budget_exceeded':True}
        self.boltz_calls+=1
        sequences=[{'protein':x} for x in args['protein_sequences']]+[{'ligand':{'id':'LIG','smiles':args['smiles']}}]
        sequences.extend({'ligand':x} for x in (args.get('co_ligand_smiles') or []))
        payload={'version':1,'sequences':sequences,'properties':[{'affinity':{'binder':'LIG'}}]}
        if args.get('pocket_residues'):payload['constraints']=[{'pocket':{'binder':'LIG','contacts':args['pocket_residues'],'max_distance':6.0,'force':True}}]
        out=self.output_dir/'gpu_calls'/f'call_{self.boltz_calls}'
        try:
            affinity=predict(payload,out,args.get('num_samples',10),self.config.seed)
            result={'call_number':self.boltz_calls,'budget_remaining':self.config.boltz_budget-self.boltz_calls,
                'affinity_data':affinity,'binding_probability':affinity['affinity_probability_binary'],'affinity_pred_value':affinity['affinity_pred_value']}
            # Preserve generated structures as accessible tool artifacts.
            self._docker_exec(['mkdir','-p','/workspace/boltz_results'],timeout=15)
            self._copy_to_container(str(out/'prediction'),f'/workspace/boltz_results/call_{self.boltz_calls}')
            result['cif_dir']=f'boltz_results/call_{self.boltz_calls}/predictions/input'
            return json.dumps(result),{'call_number':self.boltz_calls,'budget_remaining':result['budget_remaining']}
        except Exception as e:
            self.event('boltz_error',{'type':type(e).__name__,'call':self.boltz_calls})
            return 'ERROR: Boltz infrastructure failure; see audit log',{'call_number':self.boltz_calls,'infrastructure_error':True}

    def feedback(self,logger,turn):
        if self.pending is None:return None
        if self.rounds>=2:
            self.terminal_candidate=self.pending;self.pending=None
            self.event('stop',{'reason':'feedback_round_limit','candidate':self.terminal_candidate})
            return None
        failed=self.pending;self.pending=None;self.seen.add(failed);self.rounds+=1
        fp=AllChem.GetMorganFingerprint(Chem.MolFromSmiles(failed),2)
        ranked=sorted(self.pool,key=lambda x:DataStructs.TanimotoSimilarity(fp,x[1]),reverse=True)
        chosen=None
        for s,_ in ranked:
            if not self.hard(s,retrieval=True):continue
            values=self.cache.get(s)
            if values is None:
                if self.admet_calls>=self.config.admet_budget:break
                args={'smiles':s};start=time.time();text,extra=super().run_predict_admet(args)
                logger.log_tool_call(turn,'chatdrug_retrieval_predict_admet',args,text,time.time()-start,extra)
                try:values=json.loads(text)
                except ValueError:continue
                self.cache[s]=values
            if not self.admet_pass(values):continue
            # Never label a reference fully correct without budgeted target-specific binding evidence.
            if not self.boltz_context or self.boltz_calls>=self.config.boltz_budget:continue
            args={**self.boltz_context,'smiles':s};start=time.time();text,extra=self.run_predict_boltz(args)
            logger.log_tool_call(turn,'chatdrug_retrieval_predict_boltz',args,text,time.time()-start,extra)
            try:r=json.loads(text)
            except ValueError:continue
            if r.get('binding_probability',0)<=0.7:continue
            av=r['affinity_pred_value'];baseline=self.task['baseline_values']['binding_affinity']
            objectives=[x for x in self.task['optimization_objectives'] if x['property']=='binding_affinity']
            holds=[x for x in self.task['hold_constant'] if x['property']=='binding_affinity']
            if any(baseline-av<x['threshold'] for x in objectives):continue
            if any(av-baseline>x['tolerance'] for x in holds):continue
            chosen=s;break
        logger.admet_calls=self.admet_calls;logger.boltz_calls=self.boltz_calls
        self.event('ReDF',{'round':self.rounds,'generated':failed,'reference':chosen,'admet_calls':self.admet_calls,'boltz_calls':self.boltz_calls})
        if chosen:
            return f'Your provided sequence {failed} is not correct. We found reference sequence {chosen}, ranked by similarity to your proposal and verified against the other screened task conditions. Similarity to the starting molecule was not required for this reference, so it is not necessarily a valid final answer. Your submitted molecule must still meet all original task constraints, including the starting-molecule similarity requirement. Can you give me a new molecule?'
        # Match original ChatDrug: no qualifying retrieval ends this editing attempt.
        self.terminal_candidate=failed
        self.event('stop',{'reason':'no_verified_retrieval','candidate':failed})
        return f'ChatDrug retrieval found no verified correct reference for {failed} within the available corpus, evidence and remaining tool budgets. ADMET remaining: {self.config.admet_budget-self.admet_calls}; Boltz remaining: {self.config.boltz_budget-self.boltz_calls}.'

    def finalize_stopped(self):
        with tempfile.NamedTemporaryFile(mode='w',suffix='.smi') as f:
            f.write(self.terminal_candidate+'\n');f.flush()
            self._copy_to_container(f.name,'/workspace/solution.smi')
        return super().run_submit({'file_path':'solution.smi'})
