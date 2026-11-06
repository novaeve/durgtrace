from rdkit import Chem
from rdkit.Chem import Descriptors
from rdkit.Chem import QED
from toolset.sascorer import calculateScore

def calculate_logp(smiles: str) -> float:
    """
    Calculates the LogP of a molecule given its SMILES string.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string provided: {smiles}")
    logp = Descriptors.MolLogP(mol)
    
    return logp

def calculate_mr(smiles: str) -> float:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string provided: {smiles}")
    mr = Descriptors.MolMR(mol)
    return mr

def calculate_qed(smiles: str) -> float:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string provided: {smiles}")
    qed_score = QED.qed(mol)
    return qed_score

from rdkit import Chem
from rdkit.Chem import Descriptors
import math

def calculate_logp(smiles: str) -> float:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string provided: {smiles}")
    return Descriptors.MolLogP(mol)


def calculate_ring_penalty(mol) -> float:
    ring_info = mol.GetRingInfo()
    num_rings = ring_info.NumRings()
    # simple penalty used in many benchmark implementations
    return max(0, num_rings - 2)


def calculate_plogp(smiles: str) -> float:
    """
    Penalized LogP = LogP - SA penalty - ring penalty
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string provided: {smiles}")
    sa_penalty = calculateScore(mol)
    logp = Descriptors.MolLogP(mol)
    ring_penalty = calculate_ring_penalty(mol)

    plogp = logp - sa_penalty - ring_penalty

    return plogp/2