from rdkit import Chem
from rdkit.Chem import QED

def calculate_druggability(smiles):
    """
    Calculates a drug-likeness score (druggability) using RDKit's QED.
    Returns a value between 0 (poor) and 1 (high drug-likeness).
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    score = QED.qed(mol)
    return round(score, 3)