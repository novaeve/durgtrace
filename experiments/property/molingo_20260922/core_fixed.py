def smiles_post_processing(smi):
    smi = smi.replace('CF3', 'C(F)(F)(F)')
    smi = smi.replace('CCl3', 'C(Cl)(Cl)(Cl)')
    smi = smi.replace('CBr3', 'C(Br)(Br)(Br)')
    smi = smi.replace('COOH', 'C(=O)O')
    smi = smi.replace('OH', 'O')
    smi = smi.replace('CH3', 'C')
    smi = smi.replace('NH2', 'N')
    smi = smi.replace('NH3', 'N')
    smi = smi.replace('NO2', '[N+](=O)[O-]')
    smi = smi.replace('SF4', 'S(F)(F)(F)(F)')
    smi = smi.replace('SO4', 'OS(=O)(=O)O')
    smi = smi.replace('Me2', '(C)(C)')
    smi = smi.replace('Me3', '(C)(C)(C)')
    smi = smi.replace('Me', '(C)')
    return smi

def optimize_mol_tomg(smiles=None,  main_task='QED', trend='increase', variants=3, task_instruction=None):
    if trend != 'decrease':
        direction = 'increased'
    else:
        direction = 'decreased'
    
    TASK_DESCRIPTIONS = {
        'QED': f'{direction} quantitative estimate of drug-likeness (enhanced overall drug-like physicochemical properties)',
        'MR': f'{direction} molar refractivity (optimized steric bulk and polarizability for target binding)',
        'LogP': f'{direction} lipophilicity profile (optimized partition coefficient for balanced aqueous solubility and membrane permeability)'
    }

    assert task_instruction is not None or main_task in TASK_DESCRIPTIONS, f"Unsupported task: {main_task}, must be in {TASK_DESCRIPTIONS}"
    task_desc = task_instruction if task_instruction is not None else TASK_DESCRIPTIONS[main_task]


    # Step 1: Convert SMILES to natural language description
    structure, block_seq, blocks = smiles2NLdesc(smiles)
    print(structure)
    print(f"Block-level SMILES: {block_seq}")

    # Step 3: GPT suggests structural modifications
    modification_prompt = (
        f"You are a molecular chemist.\n"
        f"Consider how to optimize this molecule {smiles} for {task_desc} given its chemical structure:\n{structure}\n\n"
        f"Please suggest {variants} structural modifications.\n"
        "- For each modification, provide:\n"
        "  1. Original block: the part of the molecule you are modifying.\n"
        f"  2. Substitute block: the new functional group or atom replacement.\n"
        f"  3. Rationale: explanation of how this change could affect {main_task}\n"
        "- In the conclusion, provide a dictionary mapping the original SMILES to each alternative SMILES and rationale for the substitution.\n"
        "  Example format:\n"
        "  [\n"
        "    {\n"
        "      'Original block': '[1*]Cc1cccc(F)c1',\n"
        "      'Substitute block': '[1*]Cc1cccc(Cl)c1',\n"
        "      'Rationale': ... \n"
        "    },\n"
        "    {\n"
        "      'Original block': '[2*]NCC[1*]',\n"
        "      'Substitute block': '[2*]NCC(Cl)[1*]',\n"
        "      'Rationale': ... \n"
        "    }\n"
        "  ]\n"
        "- Make sure all alternative SMILES are valid chemical structures.\n"
        "- Ensure that each modification clearly separates Original block, Substitute block, and Rationale. NOTE: Make minimal changes (I mean only make changes if it's really help!)"
    )

    print("Optimizing molecule ...")
    modification_response = gpt_api(modification_prompt)
    results = parse_modifications(modification_response)
    for i in results:
        i['Substitute block'] = smiles_post_processing(i['Substitute block'])

    modification_dict = {}
    for b in blocks: modification_dict[b] = []
    for r in results:
        try:
            modification_dict[r['Original block']].append(r['Substitute block'])
        except:
            for k in list(modification_dict.keys()):
                kk = k.replace('[2*]', '').replace('[1*]', '').replace('()', '')
                rr = r['Original block'].replace('[2*]', '').replace('[1*]', '').replace('()', '')
                if rr == kk:
                    modification_dict[k].append(r['Substitute block'])
    
    all_block_variants = []

    for block in blocks:
        variants = [block]  # always include original block
        for alt_sm in modification_dict.get(block, []):
            if s2m(alt_sm) is not None: # Only include valid fragments
                variants.append(alt_sm)
        all_block_variants.append(variants)

    all_combinations = product(*all_block_variants)
    optimized_molecules = []
    for combo in all_combinations:
        try:
            optimized_molecules.append(reconstruct_mol("^".join(combo)))
        except:
            pass

    print(f"Number of proposed changes: {len(optimized_molecules)}")
    return optimized_molecules