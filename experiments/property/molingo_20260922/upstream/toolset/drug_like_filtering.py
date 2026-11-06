from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski



def remove_star_atoms(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles
    
    # Create an editable molecule
    rw_mol = Chem.RWMol(mol)
    
    # Identify indices of star atoms (AtomicNum 0)
    star_atoms = [atom.GetIdx() for atom in rw_mol.GetAtoms() 
                  if atom.GetAtomicNum() == 0]

    # Strategy 1: Attempt to remove them entirely
    for idx in sorted(star_atoms, reverse=True):
        rw_mol.RemoveAtom(idx)
    
    try:
        # Check if the molecule is still chemically "sane"
        Chem.SanitizeMol(rw_mol)
        return Chem.MolToSmiles(rw_mol)
    except:
        # Strategy 2: If removal fails (e.g., valence issues), replace * with C
        mol_alt = Chem.MolFromSmiles(smiles)
        rw_mol_alt = Chem.RWMol(mol_alt)
        for atom in rw_mol_alt.GetAtoms():
            if atom.GetAtomicNum() == 0:
                atom.SetAtomicNum(6) # Change 0 (Wildcard) to 6 (Carbon)
        
        Chem.SanitizeMol(rw_mol_alt)
        return Chem.MolToSmiles(rw_mol_alt)

def calculate_logS(mol, logP, mw, rot_bonds):
    aromatic_atoms = sum(
        1 for atom in mol.GetAtoms() if atom.GetIsAromatic()
    )
    heavy_atoms = mol.GetNumHeavyAtoms()
    aromatic_proportion = aromatic_atoms / heavy_atoms if heavy_atoms > 0 else 0

    logS = (
        0.16
        - 0.63 * logP
        - 0.0062 * mw
        + 0.066 * rot_bonds
        - 0.74 * aromatic_proportion
    )
    return logS

def analyze_molecule(smiles: str,
                     logS_threshold: float = -8.0,
                     relaxed_logP_limit: float = 8):
    
    if '*' in smiles:
        smiles = remove_star_atoms(smiles)
        
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False

    mw = Descriptors.MolWt(mol)
    logP = Descriptors.MolLogP(mol)
    hbd = Lipinski.NumHDonors(mol)
    hba = Lipinski.NumHAcceptors(mol)
    rot_bonds = Lipinski.NumRotatableBonds(mol)

    logS = calculate_logS(mol, logP, mw, rot_bonds)

    # Modified rule using logS
    lipinski_logS = (
        mw <= 700 and
        logP <= relaxed_logP_limit and
        logS >= logS_threshold and
        hbd <= 8 and
        hba <= 13
    )
    return lipinski_logS


if __name__ == '__main__':
    import pandas as pd
    from tqdm import tqdm

    df = pd.read_csv('/shared/nas2/thaotn2/data/corpus_all.csv')
    # df = pd.read_csv('toy_corpus.csv')
    SMILES = list(df['SMILES'].values)

    SMILES_ = []
    for sm in tqdm(SMILES):
        try:
            if analyze_molecule(sm):
                SMILES_.append(sm)
        except:
            pass
        
    with open('drug_like.txt', 'w') as f:
        f.write('\n'.join(SMILES_))