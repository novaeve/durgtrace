import torch
import torch.nn as nn
from torch_geometric.data import Data
from torch_geometric.utils import to_undirected
from rdkit import Chem, RDLogger
from rdkit.Chem import MolFromSmiles, AddHs, Descriptors, AllChem
from rdkit.Chem.rdchem import HybridizationType, BondStereo
from rdkit.Chem import MolFromSmiles as s2m
RDLogger.DisableLog('rdApp.*')

from toolset.tokenizer import get_blocks
from toolset.mol_descriptors import calculate_block_descriptors

# -----------------------------
# Utility: one-hot encoding
# -----------------------------
def one_hot_encoding(value, choices):
    return [int(value == c) for c in choices]


def one_hot_encoding_with_unknown(value, choices):
    encoding = one_hot_encoding(value, choices)
    encoding.append(int(value not in choices))
    return encoding

# -----------------------------
# Electronegativity dictionary
# -----------------------------
electronegativity = {
    'H': 2.2, 'LI': 0.98, 'BE': 1.57, 'B': 2.04, 'C': 2.55, 'N': 3.04,
    'O': 3.44, 'F': 3.98, 'NA': 0.93, 'MG': 1.31, 'AL': 1.61, 'SI': 1.9,
    'P': 2.19, 'S': 2.58, 'CL': 3.16, 'K': 0.82, 'CA': 1.0, 'SC': 1.36,
    'TI': 1.54, 'V': 1.63, 'CR': 1.66, 'MN': 1.55, 'FE': 1.83, 'CO': 1.88,
    'NI': 1.91, 'CU': 1.9, 'ZN': 1.65, 'GA': 1.81, 'GE': 2.01, 'AS': 2.18,
    'SE': 2.55, 'BR': 2.96, 'RB': 0.82, 'SR': 0.95, 'Y': 1.22, 'ZR': 1.33,
    'NB': 1.6, 'MO': 2.16, 'TC': 1.9, 'RU': 2.2, 'RH': 2.28, 'PD': 2.2,
    'AG': 1.93, 'CD': 1.69, 'IN': 1.78, 'SN': 1.96, 'SB': 2.05, 'TE': 2.1,
    'I': 2.66, 'CS': 0.79, 'BA': 0.89, 'LA': 1.1, 'CE': 1.12, 'PR': 1.13,
    'ND': 1.14, 'PM': 1.13, 'SM': 1.17, 'EU': 1.2, 'GD': 1.2, 'TB': 1.1,
    'DY': 1.22, 'HO': 1.23, 'ER': 1.24, 'TM': 1.25, 'YB': 1.1, 'LU': 1.27,
    'HF': 1.3, 'TA': 1.5, 'W': 2.36, 'RE': 1.9, 'OS': 2.2, 'IR': 2.2,
    'PT': 2.28, 'AU': 2.54, 'HG': 2.0, 'TL': 1.62, 'PB': 2.33, 'BI': 2.02,
    'PO': 2.0, 'AT': 2.2, 'FR': 0.7, 'RA': 0.9, 'AC': 1.1, 'TH': 1.3,
    'PA': 1.5, 'U': 1.38, 'NP': 1.36, 'PU': 1.28, 'AM': 1.3, 'CM': 1.3,
    'BK': 1.3, 'CF': 1.3, 'ES': 1.3, 'FM': 1.3, 'MD': 1.3, 'NO': 1.3,
    'LR': 1.3
}

# -----------------------------
# Atom features
# -----------------------------
HYBRIDIZATION_LIST = [
    HybridizationType.SP,
    HybridizationType.SP2,
    HybridizationType.SP3,
    HybridizationType.SP3D,
    HybridizationType.SP3D2,
]

def atom_features(atom):
    features = []

    # Basic atomic properties
    features.append(atom.GetAtomicNum())
    features.append(atom.GetDegree())
    features.append(atom.GetFormalCharge())
    features.append(atom.GetTotalNumHs())
    features.append(int(atom.GetIsAromatic()))
    features.append(int(atom.IsInRing()))

    # Hybridization (one-hot with unknown)
    hyb = atom.GetHybridization()
    features += one_hot_encoding_with_unknown(hyb, HYBRIDIZATION_LIST)

    # Additional chemical properties
    features.append(atom.GetMass())
    features.append(atom.GetTotalValence())
    features.append(atom.GetNumRadicalElectrons())
    features.append(int(atom.HasProp('_Chirality')))

    # Electronegativity
    symbol = atom.GetSymbol().upper()
    features.append(electronegativity.get(symbol, 0.0))  # default 0.0 if not found

    return features

# -----------------------------
# Bond features
# -----------------------------
def bond_features(bond):
    bt = bond.GetBondType()
    stereo = bond.GetStereo()

    return [
        int(bt == Chem.rdchem.BondType.SINGLE),
        int(bt == Chem.rdchem.BondType.DOUBLE),
        int(bt == Chem.rdchem.BondType.TRIPLE),
        int(bt == Chem.rdchem.BondType.AROMATIC),
        int(bond.GetIsConjugated()),
        int(bond.IsInRing()),
        int(stereo == BondStereo.STEREOZ),
        int(stereo == BondStereo.STEREOE),
        int(stereo == BondStereo.STEREOCIS),
        int(stereo == BondStereo.STEREOTRANS),
    ]

# -----------------------------
# Main conversion function
# -----------------------------
# def smiles2graph(smiles):
#     mol = Chem.MolFromSmiles(smiles)
#     mol = AddHs(mol)
#     if mol is None:
#         return None

#     # HARD cutoff: stop immediately if MW > 600
#     if Descriptors.MolWt(mol) > 600:
#         return None

#     # Node features
#     x = torch.tensor(
#         [atom_features(atom) for atom in mol.GetAtoms()],
#         dtype=torch.float
#     )

#     # Edge features
#     edge_index = []
#     edge_attr = []

#     for bond in mol.GetBonds():
#         i = bond.GetBeginAtomIdx()
#         j = bond.GetEndAtomIdx()
#         bf = bond_features(bond)

#         edge_index.append([i, j])
#         edge_attr.append(bf)

#         edge_index.append([j, i])
#         edge_attr.append(bf)

#     if edge_index:
#         edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
#         edge_attr = torch.tensor(edge_attr, dtype=torch.float)
#     else:
#         edge_index = torch.empty((2, 0), dtype=torch.long)
#         edge_attr = torch.empty((0, 10), dtype=torch.float)  # 10 bond features now

#     return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

def smiles2graph(smiles, radius=2, nBits=1024):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = AddHs(mol)

    # HARD cutoff: stop immediately if MW > 600
    if Descriptors.MolWt(mol) > 1000:
        return None

    # Node features
    x = torch.tensor([atom_features(atom) for atom in mol.GetAtoms()], dtype=torch.float)

    # Edge features
    edge_index = []
    edge_attr = []
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        bf = bond_features(bond)
        edge_index += [[i, j], [j, i]]
        edge_attr += [bf, bf]

    if edge_index:
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_attr, dtype=torch.float)
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 10), dtype=torch.float)  # 10 bond features

    # Compute Morgan fingerprint for the molecule
    morgan_fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=nBits)
    # Convert to torch tensor
    morgan_fingerprint = torch.tensor(list(morgan_fp), dtype=torch.float)

    # Return Data with morgan_fingerprint as an additional attribute
    data = Data(
        x=x,
        edge_index=edge_index,
        edge_attr=edge_attr,
    )
    data.morgan_fingerprint = morgan_fingerprint

    return data

# ---------------------------
# Hierarchical Graph (SMILES input only)
# ---------------------------
def smiles2hierarchical_graph(smiles, label=None):
    BLOCKS = get_blocks(smiles)
    if BLOCKS is None:
        return None

    BLOCKS = BLOCKS[0].replace('^','.')
    blocks = BLOCKS.split('.')
    block_label = []
    block_assignment = []
    Hs = []

    for i, block in enumerate(blocks):
        block_label.append(list(calculate_block_descriptors(block).values()))
        m = s2m(block)
        num_atoms = m.GetNumAtoms()
        block_assignment += [i]*num_atoms
        Hs.append(AddHs(m).GetNumAtoms() - num_atoms)

    for i, j in enumerate(Hs):
        block_assignment += [i]*j

    graph = smiles2graph(BLOCKS)

    # Molecule-level label
    graph.block_label = block_label
    graph.block_assignment = block_assignment
    graph.mol_label = list(calculate_block_descriptors(smiles).values())

    if label is not None:
        graph.label = label

    graph.smiles = smiles
    graph.tokenized_smiles = BLOCKS
    return graph

if __name__ == '__main__':
    import pickle
    with open('20Mdrugs.txt', 'r') as f:
        SMILES = f.readlines()
    SMILES = [i.strip() for i in SMILES]

    file = 3
    N = 50000
    st = file*N
    if (file+1)*N > len(SMILES):
        en = len(SMILES)
    else:
        en = (file+1)*N

    d = []
    for sm in SMILES[st:en]:
        try:
            g = smiles2hierarchical_graph(sm)
            if g is not None:
                d.append(g)
        except:
            print(sm)

    with open(f'graphdata{file}.pkl', 'wb') as f:
        pickle.dump(d, f)