"""Deterministic, conservative checks derived ONLY from public prompt fields.

This is a task adapter, not a semantic grader. Partial checks never certify the
whole task. No answer file or reference target is imported by this module.
"""
from collections import Counter
from functools import lru_cache
import json,re
from rdkit import Chem,RDLogger
RDLogger.DisableLog('rdApp.*')
NUM={'a':1,'an':1,'one':1,'single':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
ELEMENTS={'carbon':'C','nitrogen':'N','oxygen':'O','sulfur':'S','sulphur':'S','phosphorus':'P','fluorine':'F','chlorine':'Cl','bromine':'Br','iodine':'I','silicon':'Si','selenium':'Se','boron':'B'}
GROUPS={
 'hydroxyl':'[OX2H1]',
 'methoxy':'[O;X2]-[CH3]',
 'carbonyl':'[#6]=[#8]',
 'nitrile':'[C]#[N]',
 'nitro':'[$([N+](=O)[O-]),$([N](=O)=O)]',
 'amide':'[#6](=[#8])-[#7]',
 'ester':'[#6](=[#8])-[#8]-[#6]',
 'carboxylic_acid':'[#6](=[#8])-[OX2H1]',
 'sulfonyl':'[#16](=[#8])(=[#8])',
 'benzene':'c1ccccc1',
 'pyridine':'n1ccccc1',
 'piperidine':'[#7]1-[#6]-[#6]-[#6]-[#6]-[#6]-1',
 'piperazine':'[#7]1-[#6]-[#6]-[#7]-[#6]-[#6]-1',
 'furan':'o1cccc1',
 'thiophene':'s1cccc1',
 'cyclopropane':'[C]1-[C]-[C]-1',
 'cyclobutane':'[C]1-[C]-[C]-[C]-1',
 'cyclopentane':'[C]1-[C]-[C]-[C]-[C]-1',
 'cyclohexane':'[C]1-[C]-[C]-[C]-[C]-[C]-1',
}
QUERIES={k:Chem.MolFromSmarts(v) for k,v in GROUPS.items()}
FRAGMENTS={
 'hydroxyl':{'O':1},'methoxy':{'C':1,'O':1},'ethoxy':{'C':2,'O':1},
 'methyl':{'C':1},'ethyl':{'C':2},'n-propyl':{'C':3},'isopropyl':{'C':3},'n-butyl':{'C':4},'butyl':{'C':4},
 'vinyl':{'C':2},'allyl':{'C':3},'phenyl':{'C':6},'benzene ring':{'C':6},
 'cyclopropyl':{'C':3},'cyclobutyl':{'C':4},'cyclopentyl':{'C':5},'cyclohexyl':{'C':6},
 'fluorine':{'F':1},'fluoro':{'F':1},'chlorine':{'Cl':1},'chloro':{'Cl':1},'bromine':{'Br':1},'bromo':{'Br':1},'iodine':{'I':1},'iodo':{'I':1},
 'nitro':{'N':1,'O':2},'nitrile':{'C':1,'N':1},'cyano':{'C':1,'N':1},'trifluoromethyl':{'C':1,'F':3},'trichloromethyl':{'C':1,'Cl':3},
 'amino':{'N':1},'thiol':{'S':1},'methylamino':{'C':1,'N':1},'formyl':{'C':1,'O':1},
}

def heavy_formula(mol):
 return dict(sorted(Counter(a.GetSymbol() for a in mol.GetAtoms() if a.GetAtomicNum()>1).items()))

@lru_cache(maxsize=40000)
def descriptors(sm):
 m=Chem.MolFromSmiles(sm) if isinstance(sm,str) else None
 if m is None:return {'valid':False}
 counts=heavy_formula(m)
 return {'valid':True,'formula':json.dumps(counts,sort_keys=True),'counts':counts,'charge':sum(a.GetFormalCharge() for a in m.GetAtoms()),
         'graph_no_stereo':Chem.MolToSmiles(m,isomericSmiles=False),
         'graph_exact':Chem.MolToSmiles(m,isomericSmiles=True),
         'groups':{k:len(m.GetSubstructMatches(q)) for k,q in QUERIES.items()},
         'rings':m.GetRingInfo().NumRings()}

def value(props,key):
 if key.startswith('atom_'):return props['counts'].get(key[5:],0)
 if key.startswith('group_'):return props['groups'][key[6:]]
 return props[key]

def compare(actual,op,target):
 return {'eq':lambda:actual==target,'ge':lambda:actual>=target,'le':lambda:actual<=target}[op]()

def compile_case(case):
 rules=[];notes=[];certified=False
 text=case.get('edit_instructions',case.get('structure_description',''));low=text.lower().replace('−','-').strip()
 def add(key,op,target,evidence,rule_id):
  r={'property':key,'operator':op,'target':target,'evidence':evidence,'rule':rule_id}
  if r not in rules:rules.append(r)
 def inventory(delta,evidence,rule_id):
  counts=Counter(descriptors(case['original_smiles'])['counts']);counts.update(delta)
  if any(v<0 for v in counts.values()):notes.append('Skipped inconsistent input-derived inventory');return
  counts={k:v for k,v in counts.items() if v}
  add('formula','eq',json.dumps(counts,sort_keys=True),evidence,rule_id)
 if case['task']=='edit':
  original=case['original_smiles'];base=descriptors(original)
  # Global atom replacements are completely specified without locating a site.
  pattern=r'(?:exchange|replace|substitute) all (fluorine|chlorine|bromine|iodine|oxygen|sulfur|halogen) (?:atoms|substituents)(?: in the molecule)? (?:for|with) (fluorine|chlorine|bromine|iodine|oxygen|sulfur) atoms?(?:, leaving (?:the )?rest of the structure unchanged)?\.?'
  match=re.fullmatch(pattern,low)
  if match:
   src,dst=match.groups();m=Chem.MolFromSmiles(original);dest=ELEMENTS[dst]
   symbols={'F','Cl','Br','I'} if src=='halogen' else {ELEMENTS[src]}
   for atom in m.GetAtoms():
    if atom.GetSymbol() in symbols:atom.SetAtomicNum(Chem.GetPeriodicTable().GetAtomicNumber(dest))
   try:
    Chem.SanitizeMol(m);expected=Chem.MolToSmiles(m,isomericSmiles=True)
    add('graph_exact','eq',expected,text,'global_atom_replacement');certified=True
   except Exception:notes.append('Global atom replacement could not be sanitized; no full certification')
  # Pure rearrangements preserve heavy atom inventory. Additional chemical edits
  # are excluded; this check says nothing about whether the requested site is right.
  additional=re.search(r'\b(?:then|and (?:add|introduce|remove|replace|attach|insert|extend|shorten|delete)|at the same time|simultaneously)\b',low)
  if re.match(r'(?:relocate|reposition|rotate|tautomer\w*|protonate|deprotonate)\b',low) and not additional:
   if not re.search(r'\b(?:remove|introduce|replace|substitute|methylate|extend|shorten|cleave)\b',low):
    inventory({},text,'pure_rearrangement_heavy_inventory')
  stereo_only=(re.match(r'(?:invert|adjust|revise|set|constrain)\b',low) and re.search(r'\b(?:configuration|stereochem\w*|geometry|chiral)\b',low) and not re.search(r'\b(?:add|remove|introduce|replace|convert|relocate|protonate|deprotonate)\b',low))
  if stereo_only:add('graph_no_stereo','eq',base['graph_no_stereo'],text,'stereo_only_connectivity_invariant')
  # Explicit whole-molecule charge (not the charge on an individual atom).
  if re.search(r'(?:molecule|molecular) (?:is |becomes |remains )?neutral|neutral(?:ize|ise) the molecule|molecular neutrality|yield a neutral molecule|render the molecule neutral',low):
   add('charge','eq',0,text,'explicit_molecular_neutrality')
  if re.search(r'(?:entire |resulting )?molecule (?:becomes|is|carries|has) (?:a )?positiv(?:e|ely charged)',low):add('charge','ge',1,text,'explicit_positive_molecule')
  if re.search(r'(?:entire |resulting )?molecule (?:becomes|is|carries|has) (?:a )?negativ(?:e|ely charged)',low):add('charge','le',-1,text,'explicit_negative_molecule')
  # Single substituent additions/removals: exact heavy-atom changes, not site checks.
  names='|'.join(re.escape(x) for x in sorted(FRAGMENTS,key=len,reverse=True))
  pat=rf'^(remove|delete|excise|add|introduce|install|attach) (?:the |a |an |one |two |three )?({names}) (?:group|substituent|atom)\b'
  m=re.search(pat,low)
  if m and not additional and not re.search(r'\b(?:then|two|three|all|each|both)\b',low) and not re.search(r'\b(?:invert|protonate|deprotonate|tautomerize|condense|cyclize|connect)\b',low):
   sign=-1 if m[1] in ['remove','delete','excise'] else 1
   inventory({k:sign*v for k,v in FRAGMENTS[m[2]].items()},text,'single_substituent_inventory')
  # A sole X-to-Y substituent exchange, avoiding scaffold/fused-ring language.
  m=re.match(rf'^(?:replace|substitute) (?:the |a |an |one )?({names}) (?:group|substituent|atom)\b(.+?)\bwith (?:a |an |the )?({names})(?: (?:group|substituent|atom))?\b',low)
  if m and not additional and not re.search(r'\b(?:all|each|both|two|three|fused|tautomer\w*|cleave|protonate|deprotonate)\b',low):
   delta=Counter(FRAGMENTS[m[3]]);delta.subtract(FRAGMENTS[m[1]]);inventory(delta,text,'single_substituent_exchange_inventory')
 else:
  # Lower bounds, never sum repeated mentions of the same atom/group.
  # Local statements establish presence but not whole-molecule exact counts.
  clauses=[s.strip() for s in re.split(r'[\n;.!?]+',text) if s.strip()]
  bounds={};evidences={}
  def bound(key,n,evidence):
   if n>bounds.get(key,0):bounds[key]=n;evidences[key]=evidence
  for clause in clauses:
   cl=clause.lower()
   # Definitions involving replacement/absence can mention things not present.
   if re.search(r'\b(?:no|not|without|rather|instead|replac\w*|remov\w*|absen\w*|lack\w*)\b',cl):continue
   for name,symbol in ELEMENTS.items():
    if re.search(r'\b'+name+r'(?:s| atoms?)?\b',cl):bound('atom_'+symbol,1,clause)
    for m in re.finditer(r'\b('+ '|'.join(NUM)+r'|\d+)\s+'+name+r'(?:s| atoms?)?\b',cl):
     n=NUM[m[1]] if m[1] in NUM else int(m[1]);bound('atom_'+symbol,n,clause)
   for stem,symbol in [('fluoro','F'),('chloro','Cl'),('bromo','Br'),('iodo','I')]:
    if re.search(r'\b(?:mono|di|tri|tetra)?'+stem,cl):
     n=max([int(v) for prefix,v in [('mono',1),('di',2),('tri',3),('tetra',4)] if re.search(r'\b'+prefix+stem,cl)] or [1]);bound('atom_'+symbol,n,clause)
   # Require direct functional-group mentions; leave definitions/tautomers unknown.
   for label,pattern in [
    ('hydroxyl',r'\bhydroxyl (?:group|substituent|\()'),('methoxy',r'\bmethoxy (?:group|substituent|\()'),
    ('nitrile',r'\bnitrile\b'),('nitro',r'\bnitro (?:group|substituent|\()'),
    ('carbonyl',r'\bcarbonyl\b'),('benzene',r'\b(?:benzene|phenyl) (?:ring|group|substituent)'),
    ('pyridine',r'\bpyridine ring'),('piperidine',r'\bpiperidine ring'),('piperazine',r'\bpiperazine ring'),
    ('furan',r'\bfuran ring'),('thiophene',r'\bthiophene ring'),
    ('cyclopropane',r'\bcycloprop(?:ane|yl) ring'),('cyclobutane',r'\bcyclobut(?:ane|yl) ring'),
    ('cyclopentane',r'\bcyclopent(?:ane|yl) ring'),('cyclohexane',r'\bcyclohex(?:ane|yl) ring')]:
    if re.search(pattern,cl):bound('group_'+label,1,clause)
   if re.search(r'\b(?:amide|ester|carboxylic acid|sulfonyl) (?:group|linkage|functionality)',cl) and not re.search(r'enol|imidic|tautomer|derivative',cl):
    for label,term in [('amide','amide'),('ester','ester'),('carboxylic_acid','carboxylic acid'),('sulfonyl','sulfonyl')]:
     if re.search(r'\b'+term+r' (?:group|linkage|functionality)',cl):bound('group_'+label,1,clause)
  for key,n in bounds.items():add(key,'ge',n,evidences[key],'explicit_presence_or_local_lower_bound')
  for clause in clauses:
   cl=clause.lower()
   if re.search(r'\b(?:molecule|structure)\b',cl):
    for name,symbol in ELEMENTS.items():
     if re.search(r'\bno '+name+r' atoms?\b',cl):add('atom_'+symbol,'eq',0,clause,'explicit_global_absence')
    if re.search(r'\bno rings\b',cl):add('rings','eq',0,clause,'explicit_global_absence')
    if re.search(r'\b(?:molecule|structure) (?:is|remains) (?:electrically )?neutral\b',cl):add('charge','eq',0,clause,'explicit_molecular_neutrality')
  # Contrary lower/zero bounds mean interpretation is uncertain; withdraw both.
  keys={r['property'] for r in rules}
  for key in keys:
   rs=[r for r in rules if r['property']==key]
   if any(r['operator']=='eq' and r['target']==0 for r in rs) and any(r['operator']=='ge' and r['target']>0 for r in rs):
    rules=[r for r in rules if r['property']!=key];notes.append('Withdrawn conflicting interpretation: '+key)
 return {'rules':rules,'complete_task_verifier':certified,'unverified':[] if certified else ['Full atom connectivity, requested sites, stereochemistry and all other requirements not explicitly covered by the checks remain unverified.'],'notes':notes,'source':'public instruction and original molecule only'}

def assess(plan,smiles):
 props=descriptors(smiles)
 if not props['valid']:return {'valid':False,'checked_pass':False,'task_status':'invalid','checks':[]}
 checks=[]
 for r in plan['rules']:
  actual=value(props,r['property']);checks.append({**r,'actual':actual,'pass':compare(actual,r['operator'],r['target'])})
 passed=all(c['pass'] for c in checks)
 return {'valid':True,'checked_pass':passed,'task_status':('verified_pass' if passed else 'verified_fail') if plan['complete_task_verifier'] else ('partial_pass_unverified' if passed else 'necessary_check_failed'),'checks':checks,'unverified':plan['unverified']}

def feedback_text(result):
 if not result['valid']:return 'RDKit reports that the candidate is not a chemically valid SMILES.'
 lines=['Computed checks from the public instruction:']
 for c in result['checks']:
  if c['property'].startswith('graph_'):
   lines.append(f"{c['rule']}: {'PASS' if c['pass'] else 'FAIL'}. The check is derived from the input and instruction; no target SMILES is supplied.")
  else:lines.append(f"{c['property']}: actual={c['actual']}; required {c['operator']} {c['target']}; {'PASS' if c['pass'] else 'FAIL'}. Evidence: {c['evidence']}")
 if not result['checks']:lines.append('No task-specific condition could be reliably compiled; only SMILES validity was checked.')
 if result['task_status']!='verified_pass':lines.append('Full task correctness is NOT verified. Recheck the entire original instruction, especially site, connectivity and stereochemistry. Passing these partial checks is not proof of a correct answer.')
 return '\n'.join(lines)
