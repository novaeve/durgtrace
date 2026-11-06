######### LEAD OPTIMIZATION #########
from ast import literal_eval
from itertools import product
import numpy as np

from toolset.tokenizer import smiles2NLdesc, s2m, reconstruct_mol
from toolset.call_gpt import gpt_api
from toolset.smiles2name import smiles2name
from toolset.name2smiles import name2smiles
from toolset.ADMET import *

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

def optimize_mol(smiles=None, molecule_name=None,  uniprot_id=None, protein_name=None, disease=None, main_task='ADMET', BBBP=True, variants=20):
    if BBBP: bbbp_trend = 'higher'
    else: bbbp_trend = 'lower'

    TASK_DESCRIPTIONS = {
        'AMES': 'lower Ames mutagenicity (reduced bacterial reverse mutation risk)',
        'hERG': 'lower hERG safety (reduced potassium channel inhibition and cardiotoxicity risk)',
        'DILI': 'lower liver safety (reduced drug-induced liver injury risk)',
        'Pgp': 'lower P-glycoprotein profile (optimized efflux to balance exposure and clearance)',
        'HIA': 'higher human intestinal absorption (enhanced oral bioavailability)',
        'BBBP': f'{bbbp_trend} blood-brain barrier permeability (optimized CNS exposure)',
        'ADMET': f"""better overall ADMET properties (absorption, distribution, metabolism, excretion, toxicity):
        - lower Ames mutagenicity (reduced bacterial reverse mutation risk)
        - lower hERG safety (reduced potassium channel inhibition and cardiotoxicity risk)
        - lower liver safety (reduced drug-induced liver injury risk)
        - lower P-glycoprotein profile (optimized efflux to balance exposure and clearance)
        - higher human intestinal absorption (enhanced oral bioavailability)
        - '{bbbp_trend} blood-brain barrier permeability (optimized CNS exposure)',
        """,
    }

    assert main_task in TASK_DESCRIPTIONS, f"Unsupported task: {main_task}, must be in {TASK_DESCRIPTIONS}"
    task_desc = TASK_DESCRIPTIONS[main_task]


    if molecule_name is None and smiles is not None:
        molecule_name = smiles2name(smiles)
    if molecule_name is not None and smiles is None:
        smiles = name2smiles(molecule_name)

    # Step 1: Convert SMILES to natural language description
    structure, block_seq, blocks = smiles2NLdesc(smiles)
    print(structure)
    print(f"Block-level SMILES: {block_seq}")

    # Step 3: GPT suggests structural modifications
    modification_prompt = (
        f"You are a medicinal chemist. This molecule is the candidate drug for {disease}, targeting {protein_name} (Uniprot ID: {uniprot_id}).\n"
        f"Consider how to optimize '{molecule_name}' for {task_desc} given its chemical structure:\n{structure}\n\n"
        f"Please suggest {variants} structural modifications that could improve mentioned ADMET properties and druglikeless.\n"
        "- For each modification, provide:\n"
        "  1. Original block: the part of the molecule you are modifying.\n"
        f"  2. Substitute block: the new functional group or atom replacement. You can be creative, think about other drugs treating {disease} or targeting {protein_name} as reference.\n"
        "  3. Rationale: explanation of how this change could improve efficacy, selectivity, or ADMET properties.\n"
        "- In the conclusion, provide a dictionary mapping the original SMILES to each alternative SMILES and rationale for the substitution.\n"
        "  Example format:\n"
        "  [\n"
        "    {\n"
        "      'Original block': '[1*]Cc1cccc(F)c1',\n"
        "      'Substitute block': '[1*]Cc1cccc(Cl)c1',\n"
        "      'Rationale': 'Replacing ... with ... may improve hydrogen bonding with the target and enhance solubility.'\n"
        "    },\n"
        "    {\n"
        "      'Original block': '[2*]NCC[1*]',\n"
        "      'Substitute block': '[2*]NCC(Cl)[1*]',\n"
        "      'Rationale': 'Replacing ... with ... can improve basicity and potentially increase bioavailability.'\n"
        "    }\n"
        "  ]\n"
        "- Make sure all alternative SMILES are valid chemical structures.\n"
        "- Ensure that each modification clearly separates Original block, Substitute block, and Rationale."
    )

    print("Optimizing molecule ...")
    modification_response = gpt_api(modification_prompt)
    if 'json' in modification_response:
        results = literal_eval(modification_response.split('```json')[1].split('```')[0].strip())
    if 'python' in modification_response:
        results = literal_eval(modification_response.split('```python')[1].split('```')[0].strip())
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

    admet_profile = ADMET_Profile(smiles)[smiles]
    task_to_improve = []
    if admet_profile['AMES'] > 0.5: task_to_improve.append('AMES')
    if admet_profile['DILI'] > 0.5: task_to_improve.append('DILI')
    if admet_profile['hERG'] > 0.5: task_to_improve.append('hERG')
    if admet_profile['Pgp'] > 0.5: task_to_improve.append('Pgp')
    if admet_profile['HIA'] < 0.5: task_to_improve.append('HIA')
    if BBBP:
        if admet_profile['BBBP'] < 0.5: task_to_improve.append('BBBP')
    else:
        if admet_profile['BBBP'] > 0.5: task_to_improve.append('BBBP')

    if main_task != 'ADMET':
        ref = admet_profile[main_task]
        print('reference: ', ref)
        if main_task not in task_to_improve: print(f"{main_task} of the molecule is predicted to be good (Prob = {ref:.3f})")
        if main_task == 'AMES': t = np.array(PredictAMES(optimized_molecules)); improved = np.where(t < ref)[0]
        elif main_task == 'DILI': t = np.array(PredictDILI(optimized_molecules)); improved = np.where(t < ref)[0]
        elif main_task == 'hERG': t = np.array(PredicthERG(optimized_molecules)); improved = np.where(t < ref)[0]
        elif main_task == 'Pgp': t = np.array(PredictPgp(optimized_molecules)); improved = np.where(t < ref)[0]
        elif main_task == 'BBBP' and BBBP: t = np.array(PredictBBBP(optimized_molecules)); improved = np.where(t > ref)[0]
        elif main_task == 'BBBP' and not BBBP: t = np.array(PredictBBBP(optimized_molecules)); improved = np.where(t < ref)[0]
        else: t = np.array(PredictHIA(optimized_molecules)); improved = np.where(t > ref)[0]
    else:
        t = []
        ref = ADMET_based_scoring(list(ADMET_Profile(smiles).values())[0])[0]
        print('reference: ', ref)
        for sm in optimized_molecules:
            try:
                admet_profile = list(ADMET_Profile(sm).values())[0]
                t.append(ADMET_based_scoring(admet_profile)[0])
            except:
                t.append(ref)
        t = np.array(t)
        improved = np.where(t > ref)[0]

    print(f'Predicted {main_task} of variants: max: {t.max():.3f}, min: {t.min():.3f}, mean: {t.mean():.3f}')
    print(f'Percentage of variants with improved {main_task}: {100*len(improved)/len(t):.2f}%')
    return [optimized_molecules[i] for i in improved], [blocks, results]

def optimize_mol_tomg(smiles=None,  main_task='QED', trend='increase', variants=3):
    if trend is not 'decrease':
        direction = 'increased'
    else:
        direction = 'decreased'
    
    TASK_DESCRIPTIONS = {
        'QED': f'{direction} quantitative estimate of drug-likeness (enhanced overall drug-like physicochemical properties)',
        'MR': f'{direction} molar refractivity (optimized steric bulk and polarizability for target binding)',
        'LogP': f'{direction} lipophilicity profile (optimized partition coefficient for balanced aqueous solubility and membrane permeability)'
    }

    assert main_task in TASK_DESCRIPTIONS, f"Unsupported task: {main_task}, must be in {TASK_DESCRIPTIONS}"
    task_desc = TASK_DESCRIPTIONS[main_task]


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
    if 'json' in modification_response:
        results = literal_eval(modification_response.split('```json')[1].split('```')[0].strip())
    if 'python' in modification_response:
        results = literal_eval(modification_response.split('```python')[1].split('```')[0].strip())
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

def optimize_mol_momu(smiles=None, variants=5):
    
    # Step 1: Convert SMILES to natural language description
    structure, block_seq, blocks = smiles2NLdesc(smiles)
    print(structure)
    print(f"Block-level SMILES: {block_seq}")

    # Step 3: GPT suggests structural modifications
    modification_prompt = (
        f"You are a molecular chemist.\n"
        f"Consider how to optimize '{smiles}' given its chemical structure:\n{structure}\n\n"
        f"Please suggest {variants} structural modifications that could lead to variants of the molecule that have:"
        "- higher lipophilicity profile (optimized partition coefficient for balanced aqueous solubility and membrane permeability)"
        "- higher penalized logP (optimized lipophilicity with drug-likeness considerations such as size or synthetic feasibility)"
        "- higher molar refractivity (optimized steric bulk and polarizability for target binding)"
        "- higher quantitative estimate of drug-likeness (enhanced overall drug-like physicochemical properties)"
        "- higher blood-brain barrier permeability (optimized CNS exposure)"
        "- lower Ames mutagenicity (reduced bacterial reverse mutation risk).\n\n"
        "- For each modification, provide:\n"
        "  1. Original block: the part of the molecule you are modifying.\n"
        f"  2. Substitute block: the new functional group or atom replacement.\n"
        "  3. Rationale: explanation of how this change could improve efficacy, selectivity, or ADMET properties.\n"
        "- In the conclusion, provide a dictionary mapping the original SMILES to each alternative SMILES and rationale for the substitution.\n"
        "  Example format:\n"
        "  [\n"
        "    {\n"
        "      'Original block': '[1*]Cc1cccc(F)c1',\n"
        "      'Substitute block': '[1*]Cc1cccc(Cl)c1',\n"
        "      'Rationale': 'Replacing ... with ... may improve hydrogen bonding with the target and enhance solubility.'\n"
        "    },\n"
        "    {\n"
        "      'Original block': '[2*]NCC[1*]',\n"
        "      'Substitute block': '[2*]NCC(Cl)[1*]',\n"
        "      'Rationale': 'Replacing ... with ... can improve basicity and potentially increase bioavailability.'\n"
        "    }\n"
        "  ]\n"
        "- Make sure all alternative SMILES are valid chemical structures.\n"
        "- Ensure that each modification clearly separates Original block, Substitute block, and Rationale."
    )

    print("Optimizing molecule ...")
    modification_response = gpt_api(modification_prompt)
    if 'json' in modification_response:
        results = literal_eval(modification_response.split('```json')[1].split('```')[0].strip())
    if 'python' in modification_response:
        results = literal_eval(modification_response.split('```python')[1].split('```')[0].strip())
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


if __name__ == '__main__':
    smiles = 'O=C(Nc1cccc(/C=C/c2ccc(F)cc2)c1)c1ccccc1'
    molecule_name = None
    uniprot_id = 'P37840'
    protein_name = 'SNCA'
    disease = "Parkinson’s disease"
    main_task = 'DILI'
    BBBP = True
    variants = 20
    optimized_mol, [blocks, rationale] = optimize_mol(smiles=smiles, molecule_name=molecule_name, uniprot_id=uniprot_id, protein_name=protein_name, disease=disease, main_task=main_task, BBBP=BBBP, variants=variants)