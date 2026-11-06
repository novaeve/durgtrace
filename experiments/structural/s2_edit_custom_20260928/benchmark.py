"""S2-mini exact predicates, matching the frozen evaluate.py branches."""
from pathlib import Path
import csv, functools
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem, Descriptors
from transport import functions
RDLogger.DisableLog('rdApp.*')
ROOT=Path(__file__).resolve().parent
ns={'Chem':Chem,'DataStructs':DataStructs,'AllChem':AllChem,'Descriptors':Descriptors}
functions(ROOT/'source/s2_properties.py',['mol_prop','smiles_to_fingerprint','calculate_similarity'],ns)
mol_prop=ns['mol_prop'];calculate_similarity=ns['calculate_similarity']
ATOMS='carbon oxygen nitrogen sulfur fluorine chlorine bromine iodine phosphorus boron silicon selenium tellurium arsenic antimony bismuth polonium'.split()
GROUPS='benzene_ring hydroxyl anhydride aldehyde ketone carboxyl ester amide amine nitro halo nitrile thiol sulfide disulfide sulfoxide sulfone borane'.split()
BONDS='single double triple rotatable aromatic'.split()

def cases():
 result=[]
 for path in sorted((ROOT/'data').glob('*.csv')):
  task,sub=path.stem.split('_',1)
  for index,row in enumerate(csv.DictReader(path.open(encoding='utf-8-sig',newline=''))):
   result.append({'id':f'{path.stem}_{index:04d}','task':task,'subtask':sub,'row_index':index,'row':row,'instruction':row['Instruction'],'smiles':row.get('molecule')})
 assert len(result)==3000
 return result

def constraints(case):
 row=case['row'];sub=case['subtask'];targets={}
 if case['task']=='MolEdit':
  for field,delta in [('removed_group',-1),('added_group',1)]:
   if field in row:
    key='num_'+row[field].replace('benzene ring','benzene_ring')
    targets[key]=mol_prop(row['molecule'],key)+delta
 elif sub=='AtomNum':targets={'num_'+x:int(row[x]) for x in ATOMS}
 elif sub=='FunctionalGroup':
  # Official evaluator uses 'benzene rings'; mini CSV spells this column benzene_ring.
  # thioether is present in CSV but not in the official evaluator's group list.
  targets={'num_'+x:int(row[x]) for x in GROUPS}
 elif sub=='BondNum':
  targets={('rot_bonds' if x=='rotatable' else 'num_'+x+'_bonds'):int(row[x]) for x in BONDS if int(row[x])!=0}
 else:raise ValueError(sub)
 return targets

def evaluate(case,smiles):
 valid=bool(mol_prop(smiles,'validity')) if isinstance(smiles,str) else False
 targets=constraints(case)
 actual={k:mol_prop(smiles,k) for k in targets} if valid else {}
 result={'valid':valid,'success':valid and all(actual[k]==v for k,v in targets.items()),'actual':actual,'target':targets}
 if valid and case['task']=='MolEdit':result['similarity']=calculate_similarity(case['smiles'],smiles)
 return result

@functools.lru_cache(maxsize=40000)
def fingerprint(smiles):
 return AllChem.GetMorganFingerprint(Chem.MolFromSmiles(smiles),2)
