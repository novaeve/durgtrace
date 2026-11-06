from toolset.protein2binders import protein2binders
from toolset.calculate_druggability import calculate_druggability

def protein2chemblhit(uniprot_id, num_candidates=1):
    df = protein2binders(uniprot_id=uniprot_id)
    if len(df) > 0:
        SMILES = list(df['canonical_smiles'].values)
        SMILES = [sm for sm in SMILES if sm is not None]
        SMILES = [sm for sm in SMILES if len(sm) > 20]
        druggability = {sm:calculate_druggability(sm) for sm in SMILES}
        druggability = dict(sorted(druggability.items(), key=lambda item: item[1], reverse=True))
        binding_affinity = {}
        for sm in druggability.keys():
            binding_affinity[sm] = 1 - df[df['canonical_smiles']==sm]['standard_value'].values[0]/1000
        combined = {sm:(druggability[sm]+binding_affinity[sm])/2 for sm in druggability.keys()}
        combined = dict(sorted(combined.items(), key=lambda item: item[1], reverse=True))
        smiles = list(combined.keys())[:num_candidates]
        return smiles
    else:
        return None