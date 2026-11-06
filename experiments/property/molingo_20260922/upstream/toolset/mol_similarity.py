from rdkit.Chem import AllChem, rdShapeHelpers, rdMolAlign
from rdkit import Chem, RDLogger
from rdkit.DataStructs import TanimotoSimilarity
RDLogger.DisableLog('rdApp.*')

def tanimoto_from_smiles(smiles1, smiles2, radius=2, n_bits=2048):
    mol1 = Chem.MolFromSmiles(smiles1)
    mol2 = Chem.MolFromSmiles(smiles2)
    
    if mol1 is None or mol2 is None:
        raise ValueError("Invalid SMILES provided.")
    
    fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, radius, nBits=n_bits)
    fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, radius, nBits=n_bits)
    
    return TanimotoSimilarity(fp1, fp2)

def get_best_shape_similarity(smiles1, smiles2, num_conformers=50):
    mol1 = Chem.AddHs(Chem.MolFromSmiles(smiles1))
    mol2 = Chem.AddHs(Chem.MolFromSmiles(smiles2))

    # Generate Conformers
    ps = AllChem.ETKDGv3()
    ps.randomSeed = 42
    AllChem.EmbedMultipleConfs(mol1, num_conformers, ps)
    AllChem.EmbedMultipleConfs(mol2, num_conformers, ps)
    
    # Use MMFF properties for alignment
    pyMMFFMol1 = AllChem.MMFFGetMoleculeProperties(mol1)
    pyMMFFMol2 = AllChem.MMFFGetMoleculeProperties(mol2)

    best_shape_sim = 0

    for i in range(mol1.GetNumConformers()):
        for j in range(mol2.GetNumConformers()):
            # O3A is much better for different molecules
            # It aligns based on chemical features/force field scores
            try:
                o3a = rdMolAlign.GetO3A(mol2, mol1, pyMMFFMol2, pyMMFFMol1, prbCid=j, refCid=i)
                o3a.Align() # This physically moves mol2 to match mol1
                
                # Calculate Shape Tanimoto
                shape_sim = 1 - rdShapeHelpers.ShapeTanimotoDist(mol1, mol2, confId1=i, confId2=j)
                
                if shape_sim > best_shape_sim:
                    best_shape_sim = shape_sim
            except:
                continue

    return best_shape_sim

def combo_similarity(smiles1, smiles2, num_conformers=50, optimize=True, early_stop=0.99):
    mol1 = Chem.AddHs(Chem.MolFromSmiles(smiles1))
    mol2 = Chem.AddHs(Chem.MolFromSmiles(smiles2))

    # 1. Generate conformers
    ps = AllChem.ETKDGv3()
    ps.randomSeed = 42
    AllChem.EmbedMultipleConfs(mol1, numConfs=num_conformers, params=ps)
    AllChem.EmbedMultipleConfs(mol2, numConfs=num_conformers, params=ps)

    # 2. Optimize conformers
    if optimize:
        for conf_id in range(mol1.GetNumConformers()):
            AllChem.MMFFOptimizeMolecule(mol1, confId=conf_id)
        for conf_id in range(mol2.GetNumConformers()):
            AllChem.MMFFOptimizeMolecule(mol2, confId=conf_id)

    # 3. MMFF properties for O3A (Essential for 'Color' alignment)
    mmff1 = AllChem.MMFFGetMoleculeProperties(mol1)
    mmff2 = AllChem.MMFFGetMoleculeProperties(mol2)

    best_combo_score = 0.0

    # 4. Compare all conformer pairs
    for i in range(mol1.GetNumConformers()):
        for j in range(mol2.GetNumConformers()):
            try:
                # GetO3A performs the feature-based alignment
                o3a = rdMolAlign.GetO3A(mol2, mol1, mmff2, mmff1, prbCid=j, refCid=i)
                o3a.Align()

                # Shape Tanimoto (Volume overlap)
                shape_sim = 1 - rdShapeHelpers.ShapeTanimotoDist(mol1, mol2, confId1=i, confId2=j)

                # Color Similarity (Normalized O3A Score)
                # O3A score rewards overlap of chemically similar atom types
                color_sim_raw = o3a.Score() 
                color_sim = min(color_sim_raw / 100.0, 1.0) 
                
                combo_score = 0.5 * shape_sim + 0.5 * color_sim

                if combo_score > best_combo_score:
                    best_combo_score = combo_score

                if best_combo_score >= early_stop:
                    return best_combo_score
            except:
                continue

    return best_combo_score

if __name__ == '__main__':
    # Usage remains the same
    smiles_a = 'CCOC(=O)CN[C@H](C1CCCCC1)C(=O)N2CC[C@H]2C(=O)NCC3=CC=C(C=C3)/C(=N\\O)/N'
    smiles_b = 'CC(=O)COC(=O)CN[C@@H](C(=O)N1CC[C@H]1C(=O)NCCCc1ccc(C(N)=NO)cc1)C1CCCCC1'

    sim = combo_similarity(smiles_a, smiles_b)
    print(f"Improved Shape+Color ComboScore: {sim:.3f}")