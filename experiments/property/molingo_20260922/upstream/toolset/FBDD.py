from toolset.tokenizer import get_blocks, reconstruct_mol
from toolset.tokenizer import m2s, s2m, FragmentOnBonds
from toolset.protein2binders import protein2binders
from itertools import product
import re

def number_stars(text):
    count = 0
    def repl(match):
        nonlocal count
        count += 1
        return f"{count}*"
    return re.sub(r"\*", repl, text)

def swap_two_stars(text):
    replacements = ["2*", "1*"]
    def repl(match):
        return replacements.pop(0)
    return re.sub(r"\*", repl, text, count=2)

def FBDD(uniprot_id):
    df = protein2binders(uniprot_id)
    binders = list(df['canonical_smiles'].values)
    print(f'#Binders found for {uniprot_id}: {len(binders)}')

    CAP, BRIDGE = set(), set()

    for b in binders:
        blocks = get_blocks(b, num_tokens=3)[0].split('^')
        for block in blocks:
            if block.count('*')==1:
                CAP.add(block.replace('[1*]', '[*]').replace('[2*]', '[*]'))
            if block.count('*') == 2:
                BRIDGE.add(block.replace('[1*]', '[*]').replace('[2*]', '[*]'))
    print(f'Fragment library: #cap blocks: {len(CAP)}, #bridge blocks: {len(BRIDGE)}')

    combinations_ = list(product(CAP, BRIDGE, CAP))
    combinations = set()
    for c1, b, c2 in combinations_:
        c1 = c1.replace('[*]', '[1*]')
        c2 = c2.replace('[*]', '[2*]')
        b1 = number_stars(b)
        b2 = swap_two_stars(b)
        combinations.add(reconstruct_mol(f'{c1}^{b1}^{c2}'))
        combinations.add(reconstruct_mol(f'{c1}^{b2}^{c2}'))
    combinations = list(combinations)
    print(f'#Molecules from fragment library: {len(combinations)}')
    return combinations