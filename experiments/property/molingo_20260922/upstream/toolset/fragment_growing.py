
# with open('toolset/scaffold_core_set.txt') as f:
#     SCF = f.readlines()
#     SCF = [i.strip() for i in SCF]
# if searching_scaffolds is not None:
#     SCF = SCF[:searching_scaffolds]

# print(f'Running molecular docking between {uniprot_id} and {len(SCF)} scaffolds')
# results = []
# scores = autodockvina_docking(uniprot_id=uniprot_id, smiles=SCF, sbdd=False)[1]
# scores = [[i, j] for i, j in scores if j < -6]

# SCF = [i[0] for i in scores]
# SCORE = [i[1] for i in scores]
# SCORE = array(SCORE)
# best_candidates = [SCF[i] for i in argpartition(SCORE, 2)[:num_scaffold]]


from tqdm import tqdm
from rdkit.Chem import MolToSmiles as m2s
from rdkit.Chem import MolFromSmiles as s2m
from rdkit.Chem.Draw import MolToImage as m2i
from numpy import array, argpartition
from ast import literal_eval
from rdkit import Chem

from toolset.autodockvina_docking import autodockvina_docking
from toolset.call_gpt import gpt_api
from toolset.tokenizer import combine

from toolset.protein2binders import protein2binders
from toolset.calculate_druggability import calculate_druggability

def protein2chemblhit(uniprot_id, num_candidates=1):
    df = protein2binders(uniprot_id=uniprot_id)
    if len(df) > 0:
        SMILES = list(df['canonical_smiles'].values)
        SMILES = [sm for sm in SMILES if sm is not None]
        SMILES = [sm for sm in SMILES if len(sm) > 20]
        druggability = {sm:calculate_druggability(sm) for sm in SMILES}
        druggability = dict(sorted(druggability.items(), key=lambda item: item[1], reverse=True))
        binding_affinity = {}
        for sm in druggability.keys():
            binding_affinity[sm] = 1 - df[df['canonical_smiles']==sm]['standard_value'].values[0]/1000
        combined = {sm:(druggability[sm]+binding_affinity[sm])/2 for sm in druggability.keys()}
        combined = dict(sorted(combined.items(), key=lambda item: item[1], reverse=True))
        smiles = list(combined.keys())[:num_candidates]
        return smiles
    else:
        return None

def add_wildcard_at_index(smiles, atom_idx):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Invalid SMILES string")
    
    if atom_idx >= mol.GetNumAtoms() or atom_idx < 0:
        raise IndexError(f"Atom index {atom_idx} is out of range for this molecule.")

    rw_mol = Chem.RWMol(mol)
    new_atom = Chem.Atom(0)
    new_atom.SetIsotope(1)
    wildcard_idx = rw_mol.AddAtom(new_atom)
    rw_mol.AddBond(atom_idx, wildcard_idx, Chem.rdchem.BondType.SINGLE)
    new_mol = rw_mol.GetMol()
    Chem.SanitizeMol(new_mol)
    
    return Chem.MolToSmiles(new_mol)

def fragment_growing(smiles, uniprot_id, num_candidates=5):
    protein_name, growing_spots = autodockvina_docking(uniprot_id=uniprot_id, smiles=smiles, sbdd=True, max_hotspots=5)
    results = {}
    for _, spot in enumerate(growing_spots['growth_hotspots']):
        # Extract data
        lig_type = spot['ligand_atom_type']
        vol = spot['volume_A3']
        residues = spot['nearby_residues']

        # Structured Prompting
        prompt = f"""
Act as an expert Medicinal Chemist specializing in structure-based drug design (SBDD).

### Context
Target Protein: {protein_name} (UniProt: {uniprot_id})
Attachment Atom: {lig_type}
Available Pocket Volume: {vol} Å³
Local Environment (Nearby Residues): {residues}

### Task
1. Analyze the target's known SAR (Structure-Activity Relationship) from literature.
2. Evaluate the local pocket environment: identify potential hydrogen bond donors/acceptors, hydrophobic patches, or electrostatic interactions based on {residues}.
3. Propose {num_candidates} diverse building blocks to grow the scaffold from the {lig_type} atom.

### Constraints
- Volume: Ensure the proposed fragments fit within {vol} Å³.
- Synthetic Feasibility: Suggest fragments that are commercially available or synthetically accessible.
- Diversity: Provide a mix of aliphatic, aromatic, and polar groups if appropriate for the site, think hard at this step.

### In the conclusion, return a JSON-formatted list of dictionaries with the following keys:
```json
{{
"suggested_block": (The SMILES of the bulding block with wildcard atom (*) for connecting point.)
"rationale": (Brief explanation of the interaction with specific residues and volume fit)
}}
```
"""
        response = gpt_api(prompt)
        r = {}
        if 'json' in response:
            r = literal_eval(response.split('```json')[1].split('```')[0])
        if 'python' in response:
            r = literal_eval(response.split('```python')[1].split('```')[0])
        results[spot['ligand_atom_index']] = r

    # Grow each candidate using candidate blocks
    candidates = []
    for k, V in results.items():
        for v in V:
            try:
                frag1 = add_wildcard_at_index(smiles, k)
                frag2_ = v['suggested_block']
                frag2 = frag2_.replace('*', '[2*]')
                sm = m2s(combine(frag1, 1, frag2, 2))
                rationale =  v['rationale']
                candidates.append([sm, k, frag2_, rationale]) # variant, connecting point (attached to *), attached block, rationale
            except:
                pass
    # Check docking for each candidate
    for candidate in tqdm(candidates, desc=f'Running molecular docking with candidates:'):
        candidate.append(autodockvina_docking(smiles=candidate[0], uniprot_id=uniprot_id, sbdd=False)[1])
    
    return candidates