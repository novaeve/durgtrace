import re
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from rdkit.DataStructs import TanimotoSimilarity
from rdkit.Chem import MolToSmiles as m2s
from rdkit.Chem import MolFromSmiles as s2m
import pickle
from itertools import product
from toolset.tokenizer import *

################################################################################################
with open('/shared/nas2/shared_mol_data/tokenization/vocab_search_space.pkl', 'rb') as f:
    data = pickle.load(f)
CAP1, CAP2, CAP3, CAP4, CAP5 = data['CAP1'], data['CAP2'], data['CAP3'], data['CAP4'], data['CAP5']
BRIDGE1, BRIDGE2, BRIDGE3, BRIDGE4, BRIDGE5 = data['BRIDGE1'], data['BRIDGE2'], data['BRIDGE3'], data['BRIDGE4'], data['BRIDGE5']
BRIDGE6, BRIDGE7, BRIDGE8, BRIDGE9, BRIDGE10 = data['BRIDGE6'], data['BRIDGE7'], data['BRIDGE8'], data['BRIDGE9'], data['BRIDGE10']
BRIDGE11, BRIDGE12, BRIDGE13, BRIDGE14, BRIDGE15 = data['BRIDGE11'], data['BRIDGE12'], data['BRIDGE13'], data['BRIDGE14'], data['BRIDGE15']
BRIDGE16, BRIDGE17, BRIDGE18, BRIDGE19, BRIDGE20 = data['BRIDGE16'], data['BRIDGE17'], data['BRIDGE18'], data['BRIDGE19'], data['BRIDGE20']
BRIDGE21, BRIDGE22, BRIDGE23, BRIDGE24, BRIDGE25 = data['BRIDGE21'], data['BRIDGE22'], data['BRIDGE23'], data['BRIDGE24'], data['BRIDGE25']

def preprocessing1(sm):
    return sm.replace('[', '').replace(']', '').replace('/', '').replace('//', '').replace('\\', '').replace('\\\\', '').replace('@', '').replace('@@', '').replace('*', '')

def preprocessing2(sm):
    return re.sub(r"\d+", "", sm[3:]).replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('@', '').replace('@@', '').replace('/', '').replace('//', '').replace('\\', '').replace('\\\\', '').replace('H', '')


def find_search_space(sm, valid_space, radius=2, n_bits=2048, tanimoto_th=0.5):
    N = len(sm)
    valid_space = [i for i in valid_space if len(i) >= np.floor(N*0.5) and len(i) <= np.ceil(N*1.5)]
    search_space = []
    morgan_gen = rdFingerprintGenerator.GetMorganGenerator(
            radius=radius,
            fpSize=n_bits
        )

    mol1 = Chem.MolFromSmiles(sm)
    fp1 = morgan_gen.GetFingerprint(mol1)
    for i in valid_space:
        mol2 = Chem.MolFromSmiles(i)
        fp2 = morgan_gen.GetFingerprint(mol2)
        sim = TanimotoSimilarity(fp1, fp2)
        if sim > tanimoto_th and sim < 1: search_space.append(i)
    return list(set(search_space))


def gen_variants(sm, tanimoto_th=0.5):
    r = get_blocks(sm)
    if r is None:
        return []
    r = r[0]
    frags = [i for i in r.split('^')]

    variants = {}
    for smiles in frags:
        sm = smiles.replace('[1*]', '[*]').replace('[2*]', '[*]')
        i1 = preprocessing1(sm)[0]; i2 = preprocessing2(sm)
        search_space = []
        if sm.count('*') == 1:
            if i1=='C': search_space = find_search_space(sm, CAP1, tanimoto_th=tanimoto_th)
            if i1=='N': search_space = find_search_space(sm, CAP2, tanimoto_th=tanimoto_th)
            if i1=='O': search_space = find_search_space(sm, CAP3, tanimoto_th=tanimoto_th)
            if i1=='c': search_space = find_search_space(sm, CAP4, tanimoto_th=tanimoto_th)
            if i1=='n': search_space = find_search_space(sm, CAP5, tanimoto_th=tanimoto_th)
        if sm.count('*') == 2:
            if i1 == 'C' and 'C*' in i2: search_space = find_search_space(sm, BRIDGE1, tanimoto_th=tanimoto_th)
            if i1 == 'C' and 'N*' in i2: search_space = find_search_space(sm, BRIDGE2, tanimoto_th=tanimoto_th)
            if i1 == 'C' and 'O*' in i2: search_space = find_search_space(sm, BRIDGE3, tanimoto_th=tanimoto_th)
            if i1 == 'C' and 'c*' in i2: search_space = find_search_space(sm, BRIDGE4, tanimoto_th=tanimoto_th)
            if i1 == 'C' and 'n*' in i2: search_space = find_search_space(sm, BRIDGE5, tanimoto_th=tanimoto_th)
            if i1 == 'N' and 'C*' in i2: search_space = find_search_space(sm, BRIDGE6, tanimoto_th=tanimoto_th)
            if i1 == 'N' and 'N*' in i2: search_space = find_search_space(sm, BRIDGE7, tanimoto_th=tanimoto_th)
            if i1 == 'N' and 'O*' in i2: search_space = find_search_space(sm, BRIDGE8, tanimoto_th=tanimoto_th)
            if i1 == 'N' and 'c*' in i2: search_space = find_search_space(sm, BRIDGE9, tanimoto_th=tanimoto_th)
            if i1 == 'N' and 'n*' in i2: search_space = find_search_space(sm, BRIDGE10, tanimoto_th=tanimoto_th)
            if i1 == 'O' and 'C*' in i2: search_space = find_search_space(sm, BRIDGE11, tanimoto_th=tanimoto_th)
            if i1 == 'O' and 'N*' in i2: search_space = find_search_space(sm, BRIDGE12, tanimoto_th=tanimoto_th)
            if i1 == 'O' and 'O*' in i2: search_space = find_search_space(sm, BRIDGE13, tanimoto_th=tanimoto_th)
            if i1 == 'O' and 'c*' in i2: search_space = find_search_space(sm, BRIDGE14, tanimoto_th=tanimoto_th)
            if i1 == 'O' and 'n*' in i2: search_space = find_search_space(sm, BRIDGE15, tanimoto_th=tanimoto_th)
            if i1 == 'c' and 'C*' in i2: search_space = find_search_space(sm, BRIDGE16, tanimoto_th=tanimoto_th)
            if i1 == 'c' and 'N*' in i2: search_space = find_search_space(sm, BRIDGE17, tanimoto_th=tanimoto_th)
            if i1 == 'c' and 'O*' in i2: search_space = find_search_space(sm, BRIDGE18, tanimoto_th=tanimoto_th)
            if i1 == 'c' and 'c*' in i2: search_space = find_search_space(sm, BRIDGE19, tanimoto_th=tanimoto_th)
            if i1 == 'c' and 'n*' in i2: search_space = find_search_space(sm, BRIDGE20, tanimoto_th=tanimoto_th)
            if i1 == 'n' and 'C*' in i2: search_space = find_search_space(sm, BRIDGE21, tanimoto_th=tanimoto_th)
            if i1 == 'n' and 'N*' in i2: search_space = find_search_space(sm, BRIDGE22, tanimoto_th=tanimoto_th)
            if i1 == 'n' and 'O*' in i2: search_space = find_search_space(sm, BRIDGE23, tanimoto_th=tanimoto_th)
            if i1 == 'n' and 'c*' in i2: search_space = find_search_space(sm, BRIDGE24, tanimoto_th=tanimoto_th)
            if i1 == 'n' and 'n*' in i2: search_space = find_search_space(sm, BRIDGE25, tanimoto_th=tanimoto_th)
        variants[smiles] = search_space
    
    variants_sm = {}
    for k in variants.keys(): variants_sm[k] = set()
    if len(variants) > 0:
        for k, V in variants.items():
            if len(V) > 0:
                for i, v in enumerate(V):
                    if k.count('*') == 1:
                        if '[1*]' in k:
                            if '[*]' in v:
                                new_sm = v.replace('[*]', '[1*]')
                            else:
                                new_sm = v.replace('*', '[1*]')
                            # variants_sm.append(r.replace(k, new_sm))
                            variants_sm[k].add(new_sm)
                        if '[2*]' in k:
                            if '[*]' in v:
                                new_sm = v.replace('[*]', '[2*]')
                            else:
                                new_sm = v.replace('*', '[2*]')
                            # variants_sm.append(r.replace(k, new_sm))
                            variants_sm[k].add(new_sm)

                    if k.count('*') == 2:
                        if k.startswith('[1*]'):
                            if v.startswith('[*]'):
                                new_sm = '[1*]' + v[3:]
                                new_sm = new_sm.replace('[*]', '[2*]')
                            if v.startswith('*'):
                                new_sm = '[1*]' + v[1:]
                                new_sm = new_sm.replace('[*]', '[2*]')
                            # variants_sm.append(r.replace(k, new_sm))
                            variants_sm[k].add(new_sm)
                        else:
                            if v.startswith('[*]'):
                                new_sm = '[2*]' + v[3:]
                                new_sm = new_sm.replace('[*]', '[1*]')
                            if v.startswith('*'):
                                new_sm = '[2*]' + v[1:]
                                new_sm = new_sm.replace('[*]', '[1*]')
                            # variants_sm.append(r.replace(k, new_sm))
                            variants_sm[k].add(new_sm)

    return variants_sm


def gen_variant_molecules(smiles, tanimoto_th=0.5):
    variants = gen_variants(smiles, tanimoto_th=tanimoto_th)
    if len(variants) > 0:
        original_mol = []
        for k, v in variants.items():
            v = v.add(k); original_mol.append(k)
        combinations = set(product(*variants.values()))
        original_mol = '^'.join(original_mol)
        combinations = ['^'.join(i) for i in combinations]
        combinations = [reconstruct_mol(i) for i in combinations if i != original_mol]
        return combinations
    else:
        return []


if __name__ == '__main__':
    import signal
    from tqdm import tqdm
    import json
    import pickle

    with open('/shared/nas2/shared_mol_data/mols_w_different_scaffolds.json', 'r') as f:
        data = json.load(f)
    print(len(data))

    file = 31
    N = 3000

    class TimeoutException(Exception):
        pass

    def timeout_handler(signum, frame):
        raise TimeoutException

    signal.signal(signal.SIGALRM, timeout_handler)

    results = {}
    SMILES = list(data.values())

    for sm in tqdm(SMILES[file*N:(file+1)*N], desc=f'file: {file}'):
        try:
            signal.alarm(30)  # 30-second timeout
            variants = gen_variant_molecules(sm)
            signal.alarm(0)   # Cancel alarm if finished

            if len(variants) > 0:
                results[sm] = variants

        except TimeoutException:
            print(f"Skipped (timeout >30s): {sm}")
            continue

    with open(f'/shared/nas2/shared_mol_data/generator_data/pair{file}.pkl', 'wb') as f:
        pickle.dump(results, f)




# def get_dummy_atom_idx(m, isotope_label):
#     for atom in m.GetAtoms():
#         if atom.GetAtomicNum() == 0 and atom.GetIsotope() == isotope_label:
#             return atom.GetIdx()
#     return None

# def combine(frag1, wildcard1, frag2, wildcard2):
#     frag1, frag2 = s2m(frag1), s2m(frag2)

#     mol_dummy_idx = get_dummy_atom_idx(frag1, wildcard1)
#     frag_dummy_idx = get_dummy_atom_idx(frag2, wildcard2)
#     mol_neighbor = [nbr.GetIdx() for nbr in frag1.GetAtomWithIdx(mol_dummy_idx).GetNeighbors()][0]
#     frag_neighbor = [nbr.GetIdx() for nbr in frag2.GetAtomWithIdx(frag_dummy_idx).GetNeighbors()][0]
#     combo = Chem.CombineMols(frag1, frag2)
#     rw_combo = Chem.RWMol(combo)
#     frag_offset = frag1.GetNumAtoms()
#     rw_combo.AddBond(mol_neighbor, frag_neighbor + frag_offset, Chem.BondType.SINGLE)

#     for idx in sorted([mol_dummy_idx, frag_dummy_idx + frag_offset], reverse=True):
#         rw_combo.RemoveAtom(idx)
#     mol = rw_combo.GetMol()
#     Chem.SanitizeMol(mol)
#     return mol

# def reconstruct_mol(sm):
#     frags = sm.split('^')
#     if len(frags) > 1:
#         for i in range(len(frags)-1):
#             if i == 0:
#                 mol = combine(frags[i], 1, frags[i+1], 2)
#                 sm = m2s(mol)
#             else:
#                 mol = combine(sm, 1, frags[i+1], 2)
#                 sm = m2s(mol)
#     return sm


# CAP = [i for i in vocab.keys() if i.count('*')==1]
# BRIDGE = [i for i in vocab.keys() if i.count('*')==2]

# def preprocessing1(sm):
#     return sm.replace('[', '').replace(']', '').replace('/', '').replace('//', '').replace('\\', '').replace('\\\\', '').replace('@', '').replace('@@', '').replace('*', '')

# def preprocessing2(sm):
#     return re.sub(r"\d+", "", sm[3:]).replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('@', '').replace('@@', '').replace('/', '').replace('//', '').replace('\\', '').replace('\\\\', '').replace('H', '')

# CAP1 = [i for i in CAP if preprocessing1(i)[0]=='C']
# CAP2 = [i for i in CAP if preprocessing1(i)[0]=='N']
# CAP3 = [i for i in CAP if preprocessing1(i)[0]=='O']
# CAP4 = [i for i in CAP if preprocessing1(i)[0]=='c']
# CAP5 = [i for i in CAP if preprocessing1(i)[0]=='n']

# BRIDGE1  = [i for i in BRIDGE if preprocessing1(i)[0] == 'C' and 'C*' in preprocessing2(i)]
# BRIDGE2  = [i for i in BRIDGE if preprocessing1(i)[0] == 'C' and 'N*' in preprocessing2(i)]
# BRIDGE3  = [i for i in BRIDGE if preprocessing1(i)[0] == 'C' and 'O*' in preprocessing2(i)]
# BRIDGE4  = [i for i in BRIDGE if preprocessing1(i)[0] == 'C' and 'c*' in preprocessing2(i)]
# BRIDGE5  = [i for i in BRIDGE if preprocessing1(i)[0] == 'C' and 'n*' in preprocessing2(i)]

# BRIDGE6  = [i for i in BRIDGE if preprocessing1(i)[0] == 'N' and 'C*' in preprocessing2(i)]
# BRIDGE7  = [i for i in BRIDGE if preprocessing1(i)[0] == 'N' and 'N*' in preprocessing2(i)]
# BRIDGE8  = [i for i in BRIDGE if preprocessing1(i)[0] == 'N' and 'O*' in preprocessing2(i)]
# BRIDGE9  = [i for i in BRIDGE if preprocessing1(i)[0] == 'N' and 'c*' in preprocessing2(i)]
# BRIDGE10 = [i for i in BRIDGE if preprocessing1(i)[0] == 'N' and 'n*' in preprocessing2(i)]

# BRIDGE11 = [i for i in BRIDGE if preprocessing1(i)[0] == 'O' and 'C*' in preprocessing2(i)]
# BRIDGE12 = [i for i in BRIDGE if preprocessing1(i)[0] == 'O' and 'N*' in preprocessing2(i)]
# BRIDGE13 = [i for i in BRIDGE if preprocessing1(i)[0] == 'O' and 'O*' in preprocessing2(i)]
# BRIDGE14 = [i for i in BRIDGE if preprocessing1(i)[0] == 'O' and 'c*' in preprocessing2(i)]
# BRIDGE15 = [i for i in BRIDGE if preprocessing1(i)[0] == 'O' and 'n*' in preprocessing2(i)]

# BRIDGE16 = [i for i in BRIDGE if preprocessing1(i)[0] == 'c' and 'C*' in preprocessing2(i)]
# BRIDGE17 = [i for i in BRIDGE if preprocessing1(i)[0] == 'c' and 'N*' in preprocessing2(i)]
# BRIDGE18 = [i for i in BRIDGE if preprocessing1(i)[0] == 'c' and 'O*' in preprocessing2(i)]
# BRIDGE19 = [i for i in BRIDGE if preprocessing1(i)[0] == 'c' and 'c*' in preprocessing2(i)]
# BRIDGE20 = [i for i in BRIDGE if preprocessing1(i)[0] == 'c' and 'n*' in preprocessing2(i)]

# BRIDGE21 = [i for i in BRIDGE if preprocessing1(i)[0] == 'n' and 'C*' in preprocessing2(i)]
# BRIDGE22 = [i for i in BRIDGE if preprocessing1(i)[0] == 'n' and 'N*' in preprocessing2(i)]
# BRIDGE23 = [i for i in BRIDGE if preprocessing1(i)[0] == 'n' and 'O*' in preprocessing2(i)]
# BRIDGE24 = [i for i in BRIDGE if preprocessing1(i)[0] == 'n' and 'c*' in preprocessing2(i)]
# BRIDGE25 = [i for i in BRIDGE if preprocessing1(i)[0] == 'n' and 'n*' in preprocessing2(i)]

# data = {'CAP1': CAP1, 'CAP2': CAP2, 'CAP3': CAP3, 'CAP4': CAP4, 'CAP5': CAP5,
#         'BRIDGE1': BRIDGE1, 'BRIDGE2': BRIDGE2, 'BRIDGE3': BRIDGE3, 'BRIDGE4': BRIDGE4, 'BRIDGE5': BRIDGE5,
#         'BRIDGE6': BRIDGE6, 'BRIDGE7': BRIDGE7, 'BRIDGE8': BRIDGE8, 'BRIDGE9': BRIDGE9, 'BRIDGE10': BRIDGE10,
#         'BRIDGE11': BRIDGE11, 'BRIDGE12': BRIDGE12, 'BRIDGE13': BRIDGE13, 'BRIDGE14': BRIDGE14, 'BRIDGE15': BRIDGE15,
#         'BRIDGE16': BRIDGE16, 'BRIDGE17': BRIDGE17, 'BRIDGE18': BRIDGE18, 'BRIDGE19': BRIDGE19, 'BRIDGE20': BRIDGE20,
#         'BRIDGE21': BRIDGE21, 'BRIDGE22': BRIDGE22, 'BRIDGE23': BRIDGE23, 'BRIDGE24': BRIDGE24, 'BRIDGE25': BRIDGE25}
# import pickle
# with open('vocab_search_space.pkl', 'wb') as f:
#     pickle.dump(data, f)