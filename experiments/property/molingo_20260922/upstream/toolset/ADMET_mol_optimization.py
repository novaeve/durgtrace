from toolset.optimize_mol import optimize_mol
from toolset.ADMET import ADMET_Profile, ADMET_based_scoring 
from toolset.autodockvina_docking import docking_profile
from toolset.drug2protein import drug2protein
from toolset.gen_variants import gen_variant_molecules
from toolset.smiles2name import smiles2name
from toolset.name2smiles import name2smiles

def ADMET_filter(smiles, variants, BBBP=True, main_task=None):
    ref_profile = list(ADMET_Profile(smiles=smiles).values())[0]
    ref_score, best_score = ADMET_based_scoring(scores=ref_profile, BBBP=BBBP, main_task=main_task)
    results = {}
    if len(variants) > 0:
        for v in variants:
            admet_profile = list(ADMET_Profile(smiles=v).values())[0]
            results[v], _ = ADMET_based_scoring(scores=admet_profile, BBBP=BBBP, main_task=main_task)

        filtered_results_best = {k:v for k, v in results.items() if v == best_score - 0.5} # 0.5 is the margin
        filtered_results_acceptable = {k:v for k, v in results.items() if v > ref_score + 0.2} # 0.2
        filtered_results_acceptable = dict(sorted(filtered_results_acceptable.items(), key=lambda x: x[1], reverse=True))
        return filtered_results_best, filtered_results_acceptable, ref_profile, ref_score
    else:
        return {}, {}, {}, None

def docking_filter(smiles, protein_name, uniprot_id, filtered_results_best, filtered_results_acceptable, num_candidates=1):
    if len(filtered_results_acceptable) > 0:
        protein_targets = {protein_name: uniprot_id}

        print(f'Runing Autodock Vina between {smiles} and {list(protein_targets.keys())} ...')
        ref_docking_scores = docking_profile(smiles=smiles, protein_targets=protein_targets)
        print('Docking scores: ', ref_docking_scores)

        docking, all_docking = {}, {}

        if len(filtered_results_best) > 0:
            print(f'Runing Autodock Vina between {len(filtered_results_best)} variants and {list(protein_targets.keys())} ...')

            for k, v in filtered_results_best.items():
                d = docking_profile(k, protein_targets)
                print(f'Docking score between {k} and {list(protein_targets.keys())}: ', d)

                all_docking[k] = d

                if sum(d.values()) <= sum(ref_docking_scores.values()):
                    docking[k] = d

                if len(docking) >= num_candidates:
                    break

            return docking, all_docking, protein_targets, ref_docking_scores

        else:
            filtered_results_best = filtered_results_acceptable
            print(f'Runing Autodock Vina between {len(filtered_results_best)} variants and {list(protein_targets.keys())} ...')

            for k, v in filtered_results_acceptable.items():
                d = docking_profile(k, protein_targets)
                all_docking[k] = d

                if sum(d.values()) <= sum(ref_docking_scores.values()):
                    docking[k] = d

                if len(docking) >= num_candidates:
                    break
            return docking, all_docking, protein_targets, ref_docking_scores

    else:
        return {}, {}, {}, {}

def ADMET_mol_optimization(smiles=None, molecule_name=None, protein_name=None, uniprot_id=None, BBBP=True, efficacy=True, main_task=None, num_candidates=1):
    assert smiles is not None or molecule_name is not None, "Require at least SMILES or molecule name!"
    if molecule_name is None:
        molecule_name = smiles2name(smiles=smiles)
        print(f'Retrieved molecule name: {molecule_name} from SMILES: {smiles}')
    if smiles is None:
        smiles = name2smiles(molecule_name=molecule_name)
        print(f'Retrieved SMILES: {smiles} from molecule name: {molecule_name}')

    print('Reasoning to optimize molecule ...')
    variants = optimize_mol(smiles=smiles) # Use LLM to generate variants
    print('#variants: ', len(variants))

    print('Running ADMET prediction ...')
    filtered_results_best, filtered_results_acceptable, ref_profile, ref_score = ADMET_filter(smiles, variants, BBBP=BBBP)
    print('#candidates passed ADMET filters: ', len(filtered_results_best), len(filtered_results_acceptable))
    if efficacy:
        docking, all_docking, protein_targets, ref_docking_scores = docking_filter(smiles=smiles, protein_name=protein_name, uniprot_id=uniprot_id, filtered_results_best=filtered_results_best, filtered_results_acceptable=filtered_results_acceptable, num_candidates=num_candidates)
        if len(docking) > 0:
            print('Generate variants using heuristic ...')
            variants = gen_variant_molecules(smiles=smiles) # Use heuristic to generate variants
            print('#variants: ', len(variants))
            filtered_results_best, filtered_results_acceptable, ref_profile, ref_score = ADMET_filter(smiles, variants, BBBP=BBBP)
            print('#candidates passed ADMET filters: ', len(filtered_results_best), len(filtered_results_acceptable))
            if len(filtered_results_acceptable) > 0:
                docking, all_docking, protein_targets, ref_docking_scores = docking_filter(smiles=smiles, protein_name=protein_name, uniprot_id=uniprot_id, filtered_results_best=filtered_results_best, filtered_results_acceptable=filtered_results_acceptable, num_candidates=num_candidates)
            res = {
                'drug': smiles,
                'drug name': molecule_name,
                'drug ADMET profile': ref_profile,
                'drug ADMET score': ref_score,
                'protein targets': protein_targets,
                'drug docking scores w/ protein targets': ref_docking_scores,
                'all variants': variants,
                'variants w/ better ADMET scores': filtered_results_best,
                'variants with better docking scores': docking,
                'docking score of all variants w/ better ADMET scores': all_docking,
                }
            return res
        else:
            return {}
    
    else:
        if len(filtered_results_best) == 0:
            print('Generate variants using heuristic ...')
            variants = gen_variant_molecules(smiles=smiles) # Use heuristic to generate variants
            filtered_results_best, filtered_results_acceptable, ref_profile, ref_score = ADMET_filter(smiles, variants, BBBP=BBBP)
            res = {
                'drug': smiles,
                'drug name': molecule_name,
                'drug ADMET profile': ref_profile,
                'drug ADMET score': ref_score,
                'protein targets': {},
                'drug docking scores w/ protein targets': {},
                'all variants': variants,
                'variants w/ better ADMET scores': filtered_results_best,
                'variants with better docking scores': {},
                'docking score of all variants w/ better ADMET scores': {},
                }