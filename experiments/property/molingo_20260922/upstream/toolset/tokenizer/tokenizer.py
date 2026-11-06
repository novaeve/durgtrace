import re
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import MolToSmiles as m2s
from rdkit.Chem import MolFromSmiles as s2m
from rdkit.Chem import FragmentOnBonds
from itertools import combinations
import pickle
import json
from rdkit.Chem import BRICS
import pubchempy as pcp

from drug_like_filtering import analyze_molecule, remove_star_atoms

vocab_path = "/shared/nas2/shared_mol_data/tokenization/vocab20.json"

with open(vocab_path, "rb") as f:
    vocab = json.load(f)
vocab_sm = set(vocab.keys())

def smiles2name(smiles):
    compound = pcp.get_compounds(smiles, 'smiles')

    if compound:
        compound = compound[0]
        return compound.synonyms[0] if compound.synonyms else "N/A"
    else:
        print("No compound found for this SMILES")

def get_wildcard_pairs(mol, splitting_bonds):
    wildcard_pairs = []
    for bond in mol.GetBonds():
        if bond.GetIdx() in splitting_bonds:
            wildcard_pairs.append([bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()])
    return wildcard_pairs

def filter_close_values(values, tol=2):
    values = sorted(values)  # sort ascending
    result = []

    for v in values:
        if not result:
            result.append(v)
        elif v - result[-1] > tol:
            result.append(v)
    return result

def tokenize(mol):
    if mol is None:
        print('Invalid SMILES')
        return None, []
    if not analyze_molecule:
        print("Molecule violates Lipinski's rule of five, or contains wildcard atoms, or contains disconnected structures.")
        return mol, []

    brics_bonds = list(BRICS.FindBRICSBonds(mol))
    breakable_bonds = []
    for (a1, a2), labels in brics_bonds:
        if a1 != 0 and a2 != 0:
            bond = mol.GetBondBetweenAtoms(a1, a2)
            if bond is not None:
                breakable_bonds.append(bond.GetIdx())

    max_bonds = len(breakable_bonds)
    SPLITTING_BONDS = []

    if max_bonds > 1:
        for num_bonds in range(max_bonds, 0, -1):
            for bondset in combinations(breakable_bonds, num_bonds):
                frags_sm = m2s(FragmentOnBonds(mol, bondset)).split('.')
                if len([i for i in frags_sm if i.count('*')==1])==2 and len([i for i in frags_sm if i.count('*')>2])==0:
                    SPLITTING_BONDS.append(bondset)
                    if len(SPLITTING_BONDS) > 3:
                        return mol, SPLITTING_BONDS
            if len(SPLITTING_BONDS) > 0:
                return mol, SPLITTING_BONDS
        return mol, []
    else:
        return mol, [breakable_bonds]
        
def find_next_token(bond_pairs, frags_sm, begin):
    a, b = next(p for p in bond_pairs if begin in p)
    end = b if begin == a else a
    tag = f'[{end}*]'

    for sm in frags_sm:
        if tag in sm:
            temp = sm.replace(tag, '')
            try:
                n = int(re.search(r"\[(\d+)\*\]", temp).group(1))
                if n != 2:
                    sm = sm.replace(tag, '[2*]').replace(f'[{n}*]', '[1*]')
                else:
                    if end != 1:
                        sm = sm.replace(f'[{n}*]', '[1*]').replace(tag, '[2*]')
                    else:
                        sm = sm.replace(f'[{n}*]', '[3*]').replace(tag, '[2*]').replace(f'[3*]', '[1*]')
                return sm, n
            except:
                sm = sm.replace(tag, '[2*]')
    return None, None

def get_blocks_(smi: str, num_tokens: int = 3, return_bonds=False):
    mol = s2m(smi)
    try:
        mol, splitting_bonds_groups_ = tokenize(mol)
        splitting_bonds_groups = [filter_close_values(i) for i in splitting_bonds_groups_]

        if mol is None or len(splitting_bonds_groups) == 0:
            return ((smi, smi), mol, []) if return_bonds else (smi, smi)

        best_result = None
        best_std = float("inf")
        best_bonds = []

        # Repeat the process for each group of splitting bonds
        for splitting_bonds in splitting_bonds_groups:
            if len(splitting_bonds) == 0:
                continue

            # --- initial fragmentation ---
            fragments = FragmentOnBonds(mol, splitting_bonds, addDummies=True)
            frags_sm = m2s(fragments).split(".")
            frags_sm = [re.sub(r"\[\d+\*\]", "[*]", sm) for sm in frags_sm]

            require_vocab = all(f in vocab_sm for f in frags_sm)
            n = len(splitting_bonds)

            # --- simple case: single split ---
            if n == 1:
                a = frags_sm[0].replace("[*]", "[1*]")
                b = frags_sm[1].replace("[*]", "[2*]")
                r = (
                    f"{a}^{b}",
                    f"{b.replace('[2*]', '[1*]')}^{a.replace('[1*]', '[2*]')}",
                )
                std = 0  # only two fragments
                if std < best_std:
                    best_result = r
                    best_std = std
                    best_bonds = splitting_bonds
                continue

            # --- generate and score combinations on the fly ---
            best_per_token_count = {}  # num_tokens -> (std, bonds)
            for i in range(1, n + 1):
                for bonds_candidate in combinations(splitting_bonds, i):
                    fragments_candidate = FragmentOnBonds(mol, bonds_candidate, addDummies=True)
                    frags_candidate = m2s(fragments_candidate).split(".")
                    frags_candidate = [re.sub(r"\[\d+\*\]", "[*]", sm) for sm in frags_candidate]

                    if require_vocab:
                        vals = [vocab.get(f, None) for f in frags_candidate]
                        if None in vals:
                            continue
                    else:
                        vals = [vocab.get(f, 0) for f in frags_candidate]

                    std = np.array(vals).std()
                    t = len(frags_candidate)

                    if t not in best_per_token_count or std < best_per_token_count[t][0]:
                        best_per_token_count[t] = (std, bonds_candidate)

            if not best_per_token_count:
                continue

            min_tokens = min(best_per_token_count.keys())
            nt = max(num_tokens, min_tokens)
            if nt not in best_per_token_count:
                continue

            bonds = best_per_token_count[nt][1]
            std = best_per_token_count[nt][0]

            if std >= best_std:
                continue  # only keep best across all groups

            # --- final fragmentation ---
            fragments = FragmentOnBonds(mol, bonds, addDummies=True)
            frags_sm = m2s(fragments).split(".")
            if len(frags_sm) == 0:
                continue

            bond_pairs = [
                [b.GetBeginAtomIdx(), b.GetEndAtomIdx()]
                for b in mol.GetBonds()
                if b.GetIdx() in bonds
            ]

            first_tokens = [i for i in frags_sm if i.count("*") == 1]
            if len(first_tokens) != 2:
                continue

            # --- build token sequences ---
            case1 = []
            first = first_tokens[0]
            number = int(re.search(r"\[(\d+)\*\]", first).group(1))
            case1.append(first.replace(f"[{number}*]", "[1*]"))

            for _ in range(nt - 2):
                sm, number = find_next_token(bond_pairs, frags_sm, number)
                case1.append(sm)

            last = first_tokens[1]
            number = int(re.search(r"\[(\d+)\*\]", last).group(1))
            case1.append(last.replace(f"[{number}*]", "[2*]"))

            case2 = case1[::-1]
            case2 = [
                i.replace("[2*]", "__tmp__")
                 .replace("[1*]", "[2*]")
                 .replace("__tmp__", "[1*]")
                for i in case2
            ]

            best_result = ("^".join(case1), "^".join(case2))
            best_std = std
            best_bonds = bonds

        if best_result is None:
            return ((smi, smi), mol, []) if return_bonds else (smi, smi)
        return (best_result, mol, best_bonds) if return_bonds else best_result

    except Exception:
        # fallback if anything fails
        return ((smi, smi), mol, []) if return_bonds else (smi, smi)

def get_blocks(smiles):
    r = []
    if '.' in smiles:
        for i in smiles.split('.'):
            r.append(get_blocks_(i))
        r0 = '.'.join([i[0] for i in r])
        r1 = '.'.join([i[1] for i in r])
        return (r0, r1)
    else:
        return get_blocks_(smiles)

def smiles2blocks(smiles):
    blocks = get_blocks(smiles)[0].replace('.', '^').split('^')
    return {i:smiles2name(remove_star_atoms(i)) for i in blocks}

def smiles2NLdesc(sm):
    sm2b = smiles2blocks(sm)
    txt = []
    for k, v in sm2b.items():
        txt.append(f'{v} (SMILES: {k})')
    txt = ', '.join(txt)
    txt = f'The molecule is composed of the following sequence of building blocks: {txt}, with [1*] always connects with [2*] in the next block, and [2*] always connect with [1*] in the next block.'
    return txt

#################### MOL RECONSTRUCTION ####################
def get_dummy_atom_idx(mol, isotope_label):
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 0 and atom.GetIsotope() == isotope_label:
            return atom.GetIdx()
    return None

def combine(frag1, wildcard1, frag2, wildcard2):
    frag1, frag2 = s2m(frag1), s2m(frag2)

    mol_dummy_idx = get_dummy_atom_idx(frag1, wildcard1)
    frag_dummy_idx = get_dummy_atom_idx(frag2, wildcard2)
    mol_neighbor = [nbr.GetIdx() for nbr in frag1.GetAtomWithIdx(mol_dummy_idx).GetNeighbors()][0]
    frag_neighbor = [nbr.GetIdx() for nbr in frag2.GetAtomWithIdx(frag_dummy_idx).GetNeighbors()][0]
    combo = Chem.CombineMols(frag1, frag2)
    rw_combo = Chem.RWMol(combo)
    frag_offset = frag1.GetNumAtoms()
    rw_combo.AddBond(mol_neighbor, frag_neighbor + frag_offset, Chem.BondType.SINGLE)

    for idx in sorted([mol_dummy_idx, frag_dummy_idx + frag_offset], reverse=True):
        rw_combo.RemoveAtom(idx)
    mol = rw_combo.GetMol()
    Chem.SanitizeMol(mol)
    return mol

def reconstruct_mol(sm):
    frags = sm.split('^')
    if len(frags) > 1:
        for i in range(len(frags)-1):
            if i == 0:
                mol = combine(frags[i], 1, frags[i+1], 2)
                sm = m2s(mol)
            else:
                mol = combine(sm, 1, frags[i+1], 2)
                sm = m2s(mol)
    return sm
#################### END MOL RECONSTRUCTION ####################


if __name__ == "__main__":
    num_tokens = 3
    sm = 'C1=CC(=NC=C1/C=C/C(=O)NCC2=CC3=C(C(=CC(=C3)C4=CC=C(C=C4)C(=O)N5CCC(CC5)(F)F)C6=CC=C(C=C6)F)O2)N'
    r = get_blocks(sm, num_tokens)