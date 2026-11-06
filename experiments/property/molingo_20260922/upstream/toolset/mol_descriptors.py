from rdkit.Chem import MolFromSmiles, AddHs
from rdkit.Chem import Descriptors, rdMolDescriptors, Crippen, Lipinski, AllChem
from rdkit.Chem import EState


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

def calculate_block_descriptors(smiles):
    mol = MolFromSmiles(smiles)
    descriptors = {}
    if mol is not None:
        # =========================
        # 1. Physicochemical Descriptors
        # =========================
        logP = Descriptors.MolLogP(mol)
        mw = Descriptors.MolWt(mol)
        rot_bonds = Descriptors.NumRotatableBonds(mol)

        descriptors['MolecularWeight'] = mw
        descriptors['LogS'] = calculate_logS(mol, logP, mw, rot_bonds)
        descriptors['TPSA'] = rdMolDescriptors.CalcTPSA(mol)
        descriptors['NumHDonors'] = Lipinski.NumHDonors(mol)
        descriptors['NumHAcceptors'] = Lipinski.NumHAcceptors(mol)
        descriptors['NumRotatableBonds'] = rot_bonds
        descriptors['FractionCSP3'] = rdMolDescriptors.CalcFractionCSP3(mol)
        
        # =========================
        # 2. Structural Descriptors
        # =========================
        descriptors['RingCount'] = rdMolDescriptors.CalcNumRings(mol)
        descriptors['AromaticRingCount'] = rdMolDescriptors.CalcNumAromaticRings(mol)
        descriptors['NumHeteroatoms'] = rdMolDescriptors.CalcNumHeteroatoms(mol)
        descriptors['NumHeavyAtoms'] = Descriptors.HeavyAtomCount(mol)
        descriptors['NumAliphaticRings'] = rdMolDescriptors.CalcNumAliphaticRings(mol)
        descriptors['NumAromaticHeterocycles'] = rdMolDescriptors.CalcNumAromaticHeterocycles(mol)
        descriptors['NumSaturatedRings'] = rdMolDescriptors.CalcNumSaturatedRings(mol)

        estates = EState.EStateIndices(mol)
        if estates.size > 0:  # <-- check array size instead of truth value
            descriptors['MinEState'] = float(estates.min())
            descriptors['MaxEState'] = float(estates.max())
            descriptors['MeanEState'] = float(estates.mean())
        else:
            descriptors['MinEState'] = descriptors['MaxEState'] = descriptors['MeanEState'] = None
    return descriptors

def calculate_mol_descriptors(smiles):
    mol = MolFromSmiles(smiles)
    descriptors = {}
    if mol is not None:
        descriptors = Descriptors.CalcMolDescriptors(mol)
    del descriptors['BCUT2D_MWHI']; del descriptors['BCUT2D_MWLOW']; del descriptors['BCUT2D_CHGHI']; del descriptors['BCUT2D_CHGLO']; del descriptors['BCUT2D_LOGPHI']; del descriptors['BCUT2D_LOGPLOW']; del descriptors['BCUT2D_MRHI']; del descriptors['BCUT2D_MRLOW']; 
    return descriptors

        
if __name__ == '__main__':
    import pandas as pd
    from tqdm import tqdm
    import pickle

    with open('drug_like.txt', 'r') as f: SM = f.readlines()
    SM = [i.strip() for i in SM]
    print(len(SM))

    d = {}
    for sm in tqdm(SM):
        d[sm] = calculate_descriptors(sm)

    with open('buildingblock2descriptor.pkl', 'wb') as f:
        pickle.dump(d, f)