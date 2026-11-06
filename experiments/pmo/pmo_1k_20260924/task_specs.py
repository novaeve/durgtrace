"""Task instructions grounded in PyTDC PMO scoring, not MT-Mol constraints."""
TASKS = {
'albuterol_similarity': ('Albuterol_Similarity','Maximize FCFP4 Tanimoto similarity to albuterol; similarity is scaled to reach score 1 at 0.75.'),
'amlodipine_mpo': ('Amlodipine_MPO','Maximize the geometric mean of ECFP4 similarity to amlodipine and a Gaussian ring-count score centered at 3 rings (sigma 0.5).'),
'celecoxib_rediscovery': ('Celecoxib_Rediscovery','Rediscover celecoxib by maximizing ECFP4 Tanimoto similarity to celecoxib.'),
'deco_hop': ('Deco Hop','Decoration hopping: preserve SMARTS [#7]-c1n[c;h1]nc2[c;h1]c(-[#8])[c;h0][c;h1]c12; remove CS([#6])(=O)=O and [#7]-c1ccc2ncsc2c1 decorations; maximize pharmacophore similarity to CCCOc1cc2ncnc(Nc3ccc4ncsc4c3)c2cc1S(=O)(=O)C(C)(C)C, saturating at 0.85. The oracle combines these scores.'),
'drd2': ('DRD2','Maximize predicted DRD2 activity probability returned by the fixed PMO DRD2 classifier.'),
'fexofenadine_mpo': ('Fexofenadine_MPO','Maximize the geometric mean of atom-pair similarity to fexofenadine (saturating at 0.8), TPSA at least 90 (penalty below, sigma 10), and RDKit LogP at most 4 (penalty above, sigma 1).'),
'gsk3b': ('GSK3B','Maximize predicted GSK3B activity probability returned by the fixed PMO GSK3B classifier.'),
'isomers_c7h8n2o2': ('Isomers_C7H8N2O2','Generate different valid molecular structures matching molecular formula C7H8N2O2. The oracle rewards correct element counts and total atom count.'),
'isomers_c9h10n2o2pf2cl': ('Isomers_C9H10N2O2PF2Cl','Generate different valid molecular structures matching molecular formula C9H10N2O2PF2Cl. The oracle rewards correct element counts and total atom count.'),
'jnk3': ('JNK3','Maximize predicted JNK3 inhibitory activity probability returned by the fixed PMO JNK3 classifier.'),
'median1': ('Median 1','Maximize the geometric mean of ECFP4 similarities to both camphor (CC1(C)C2CCC1(C)C(=O)C2) and menthol (CC(C)C1CCC(C)CC1O).'),
'median2': ('Median 2','Maximize the geometric mean of ECFP6 similarities to both tadalafil and sildenafil.'),
'mestranol_similarity': ('Mestranol_Similarity','Maximize atom-pair Tanimoto similarity to mestranol; similarity is scaled to reach score 1 at 0.75.'),
'osimertinib_mpo': ('Osimertinib_MPO','Maximize the geometric mean of FCFP4 similarity to osimertinib (saturating at 0.8), ECFP6 similarity at most 0.85 (penalty above, sigma 0.1), TPSA at least 100 (penalty below, sigma 10), and RDKit LogP at most 1 (penalty above, sigma 1).'),
'perindopril_mpo': ('Perindopril_MPO','Maximize the geometric mean of ECFP4 similarity to perindopril and a Gaussian aromatic-ring count score centered at 2 (sigma 0.5).'),
'qed': ('QED','Maximize the RDKit quantitative estimate of drug-likeness (QED), towards 1.'),
'ranolazine_mpo': ('Ranolazine_MPO','Maximize the geometric mean of atom-pair similarity to ranolazine (saturating at 0.7), TPSA at least 95 (penalty below, sigma 20), RDKit LogP at least 7 (penalty below, sigma 1), and fluorine count close to 1 (Gaussian sigma 1).'),
'scaffold_hop': ('Scaffold Hop','Scaffold hopping: remove SMARTS [#7]-c1n[c;h1]nc2[c;h1]c(-[#8])[c;h0][c;h1]c12; preserve decoration SMARTS [#6]-[#6]-[#6]-[#8]-[#6]~[#6]~[#6]~[#6]~[#6]-[#7]-c1ccc2ncsc2c1; maximize pharmacophore similarity to CCCOc1cc2ncnc(Nc3ccc4ncsc4c3)c2cc1S(=O)(=O)C(C)(C)C, saturating at 0.75. The oracle combines these scores.'),
'sitagliptin_mpo': ('Sitagliptin_MPO','Maximize a geometric mean combining LOW ECFP4 similarity to sitagliptin (Gaussian centered at zero, sigma 0.1), matching its RDKit LogP (sigma 0.2) and TPSA (sigma 5), and matching molecular formula C16H15F6N5O.'),
'thiothixene_rediscovery': ('Thiothixene_Rediscovery','Rediscover thiothixene by maximizing ECFP4 Tanimoto similarity to thiothixene.'),
'troglitazon_rediscovery': ('Troglitazone_Rediscovery','Rediscover troglitazone by maximizing ECFP4 Tanimoto similarity to troglitazone.'),
'valsartan_smarts': ('Valsartan_Smarts','Maximize the geometric mean of presence of SMARTS CN(C=O)Cc1ccc(c2ccccc2)cc1, and Gaussian matches to the RDKit LogP, TPSA and Bertz complexity of NC(CC(=O)N1CCn2c(nnc2C(F)(F)F)C1)Cc1cc(F)c(F)cc1F (sigmas 0.2, 5 and 30 respectively).'),
'zaleplon_mpo': ('Zaleplon_MPO','Maximize the geometric mean of ECFP4 similarity to zaleplon and matching molecular formula C19H17N3O2.'),
}

def instruction(task):
    return (f'PMO molecular optimization objective: {task}. '+TASKS[task][1]+
            ' Scores range from 0 to 1; higher is better. Search for multiple distinct high-scoring molecules over the run.')
