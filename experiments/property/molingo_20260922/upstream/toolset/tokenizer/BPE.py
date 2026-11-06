from medicas_tokenizer import tokenize
from drug_like_filtering import analyze_molecule

from rdkit.Chem import MolToSmiles as m2s
from rdkit.Chem import MolFromSmiles as s2m
from rdkit.Chem.Draw import MolToImage as m2i
from rdkit.Chem import FragmentOnBonds
import pickle
from itertools import combinations
from tqdm import tqdm
import re
import os

FRAGMENTS = []

corpus_path = "/shared/nas2/shared_mol_data/tokenization/drug_like.txt"
with open(corpus_path) as f:    
    SMILES = f.readlines()
SMILES = [i.strip() for i in SMILES]

file = 3
N = 5000000
for sm in tqdm(SMILES[file*N:(file+1)*N], desc=f'file: {file}'):
    fragments = []
    if analyze_molecule:
        try:
            mol = s2m(sm)
            mol, splitting_bonds = tokenize(mol)
            for bs in splitting_bonds:
                if len(bs) >= 2:
                    min_bonds = 2
                    bondsets = list(combinations(bs, min_bonds))
                    for bondset in bondsets:
                        frags_sm = m2s(FragmentOnBonds(mol, bondset)).split('.')
                        caps = 0
                        for sm in frags_sm:
                            if sm.count('*') > 2:
                                continue
                            if sm.count('*') == 1:
                                caps += 1
                        if caps == 2:
                            frags_sm = [re.sub(r"\[\d+\*\]", "[*]", sm) for sm in frags_sm]
                            fragments.extend(frags_sm)
                    
                    min_bonds = 1
                    bondsets = list(combinations(bs, min_bonds))
                    for bondset in bondsets:
                        frags_sm = m2s(FragmentOnBonds(mol, bondset)).split('.')
                        caps = 0
                        for sm in frags_sm:
                            if sm.count('*') > 2:
                                continue
                            if sm.count('*') == 1:
                                caps += 1
                        if caps == 2:
                            frags_sm = [re.sub(r"\[\d+\*\]", "[*]", sm) for sm in frags_sm]
                            fragments.extend(frags_sm)
                if len(bs) == 1:
                    frags_sm = m2s(FragmentOnBonds(mol, bs)).split('.')
                    frags_sm = [re.sub(r"\[\d+\*\]", "[*]", sm) for sm in frags_sm]
                    fragments.extend(frags_sm)
            fragments = list(set(fragments))
            FRAGMENTS.extend(fragments)
        except:
            print(sm)

save_path = f'/shared/nas2/shared_mol_data/tokenization/BPE{file}.pkl'
with open(save_path, 'wb') as f:
    pickle.dump(FRAGMENTS, f)
