"""Documented SMDD port of existing AgentDrug multi-property refinement.

Public task conditions replace original descriptor predicates. Every learned
oracle query, including retrieval, consumes the shared per-task SMDD budget.
No-reference feedback continues (unlike ChatDrug); final generation is retained.
"""
import csv,json,pathlib,re,tempfile,time
from rdkit import Chem,DataStructs
from rdkit.Chem import AllChem
from chatdrug_adapter import ChatDrugExecutor
from agent_harness.tools import ToolExecutor
from agent_harness.agent_loop import AgentResult
from transport_adapter import request
ROOT=pathlib.Path(__file__).resolve().parent
def protein_inputs(path):
 mapping=dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),'ARNDCQEGHILKMFPSTWYV'));mapping.update(MSE='M')
 chains={};seen=set()
 for line in pathlib.Path(path).read_text().splitlines():
  if line.startswith('ENDMDL'):break
  if not line.startswith('ATOM  '):continue
  chain=line[21].strip() or 'A';residue=(chain,line[22:27])
  if residue in seen:continue
  seen.add(residue);chains.setdefault(chain,[]).append(mapping.get(line[17:20].strip(),'X'))
 return [{'id':c,'sequence':''.join(seq)} for c,seq in chains.items()]

class AgentDrugExecutor(ChatDrugExecutor):
 def __init__(self,*args):
  super().__init__(*args)
  self.audit=self.output_dir/'agentdrug_events.jsonl'
  self.pool=[]
  for row in csv.DictReader((ROOT/'retrieval.csv').open()):
   mol=Chem.MolFromSmiles(row['sequence'])
   if mol is not None and Chem.MolToSmiles(mol,isomericSmiles=True)!=self.reference_smiles:
    self.pool.append((row['sequence'],AllChem.GetMorganFingerprint(mol,2)))
  self.evidence={};self.binding={}
  # Protein sequence and pocket positions are public inputs, not witness data.
  self.proteins=protein_inputs(self.task_dir/'complex.pdb')
  pocket=re.search(r'The pocket is defined.*?: (.*?)(?:\n|$)',self.task['description'])
  self.contacts=[[c,int(n)] for c,n in re.findall(r'([A-Za-z0-9]+):(\d+)',pocket.group(1) if pocket else '')]
  self.event('protocol',{'max_generations':5,'max_output_tokens':256,'retrieval_rows':len(self.pool),'protein_chain_ids':[p['id'] for p in self.proteins],'pocket_count':len(self.contacts)})
 def admet(self,s):
  if s in self.evidence:return self.evidence[s]
  if self.admet_calls>=self.config.admet_budget:return None
  text,extra=ToolExecutor.run_predict_admet(self,{'smiles':s})
  try:values=json.loads(text)
  except ValueError:values=None
  self.event('admet',{'smiles':s,'values':values,'extra':extra})
  if values is not None:self.evidence[s]=values
  return values
 def bind(self,s):
  if s in self.binding:return self.binding[s]
  if self.boltz_calls>=self.config.boltz_budget:return None
  text,extra=self.run_predict_boltz({'smiles':s,'protein_sequences':self.proteins,'pocket_residues':self.contacts,'num_samples':10})
  try:value=json.loads(text)
  except ValueError:value=None
  self.event('binding',{'smiles':s,'value':value,'extra':extra})
  if value is not None:self.binding[s]=value
  return value
 def binding_pass(self,value):
  if not value or value.get('binding_probability',0)<=0.7:return False
  av=value.get('affinity_pred_value');bv=self.task['baseline_values'].get('binding_affinity')
  for x in self.task['optimization_objectives']:
   if x['property']=='binding_affinity' and (bv is None or av is None or bv-av<x['threshold']):return False
  for x in self.task['hold_constant']:
   if x['property']=='binding_affinity' and (bv is None or av is None or av-bv>x['tolerance']):return False
  return True
 def assess(self,s):
  mol=Chem.MolFromSmiles(s)
  if mol is None:return False,'Validity:\nThe modified molecule is not chemically valid.'
  hard=self.hard(s);values=self.admet(s)
  feedback='Validity:\nThe modified molecule is chemically valid.\nDesired property:\n'+json.dumps({'hard_constraints_pass':hard,'measured_admet':values,'baseline_values':self.task['baseline_values'],'objectives':self.task['optimization_objectives'],'hold_constant':self.task['hold_constant']})
  okay=hard and values is not None and self.admet_pass(values)
  if okay:
   binding=self.bind(s);okay=self.binding_pass(binding);feedback+='\nBinding evidence: '+json.dumps(binding)
  feedback+=f'\nRemaining oracle budget: ADMET {self.config.admet_budget-self.admet_calls}, Boltz {self.config.boltz_budget-self.boltz_calls}. Missing evidence is unverified.'
  return okay,feedback
 def retrieve(self,s):
  mol=Chem.MolFromSmiles(s)
  if mol is None:return None
  fp=AllChem.GetMorganFingerprint(mol,2)
  for candidate,_ in sorted(self.pool,key=lambda x:DataStructs.TanimotoSimilarity(fp,x[1]),reverse=True):
   if self.admet_calls>=self.config.admet_budget and candidate not in self.evidence:break
   # Original AgentDrug retrieves property-qualified examples without a fixed
   # similarity cutoff; SMDD hard constraints are required to call one correct.
   if not self.hard(candidate,retrieval=True):continue
   value=self.admet(candidate)
   if value is None or not self.admet_pass(value):continue
   if self.binding_pass(self.bind(candidate)):return candidate
  return None

def run_agent(task_yaml,task_dir,config,container_id,output_dir):
 e=AgentDrugExecutor(container_id,config,task_yaml,task_dir,output_dir)
 original=task_yaml['description']+'\nRespond with only the SMILES string of your modified molecule. No explanation is needed.\n\nMolecule:'+e.reference_smiles+'\nAnswer:'
 prompt=original;intokens=outtokens=0;candidate='';stop='refinement_limit'
 for generation in range(1,6):
  response=request([{'role':'user','content':prompt}],temperature=0,max_tokens=256)
  usage=response.get('usage',{});intokens+=usage.get('prompt_tokens',0);outtokens+=usage.get('completion_tokens',0)
  raw=response['choices'][0]['message'].get('content') or ''
  candidate=raw.strip()
  if '->' in candidate:candidate=candidate.split('->')[1].strip()
  if 'becomes' in candidate:candidate=candidate.split('becomes')[1].strip()
  e.event('generation',{'generation':generation,'prompt':prompt,'response':response,'candidate':candidate})
  if generation==5:break
  if intokens+outtokens>=config.max_tokens:stop='token_budget_exceeded';break
  hit,feedback=e.assess(candidate)
  if hit:stop='public_conditions_satisfied';break
  reference=e.retrieve(candidate)
  if reference:feedback+=f'\n\nFor your reference, we find a molecule {reference} which is correct and similar to your modified molecule.'
  e.event('feedback',{'generation':generation,'feedback':feedback,'reference':reference})
  prompt=original+candidate+f'\n\nImprove the modified molecule based on the following feedback:\n{feedback}\nRespond with only the SMILES string of your modified molecule. No explanation is needed.'
 e.terminal_candidate=candidate;e.finalize_stopped()
 e.event('stop',{'reason':stop,'candidate':candidate,'generations':generation,'admet_calls':e.admet_calls,'boltz_calls':e.boltz_calls})
 return AgentResult(status='submitted',turns_used=generation,total_input_tokens=intokens,total_output_tokens=outtokens,admet_calls=e.admet_calls,boltz_calls=e.boltz_calls,submitted_file='solution.smi')
