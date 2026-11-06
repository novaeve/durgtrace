
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

def compute_scores(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    # --- Lipinski ---
    lipinski_score = sum([
        Descriptors.MolWt(mol) <= 500,
        Descriptors.MolLogP(mol) <= 5,
        Lipinski.NumHDonors(mol) <= 5,
        Lipinski.NumHAcceptors(mol) <= 10
    ])

    # --- Veber ---
    veber_score = sum([
        Lipinski.NumRotatableBonds(mol) <= 10,
        rdMolDescriptors.CalcTPSA(mol) <= 140
    ])

    # --- PAINS ---
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    catalog = FilterCatalog(params)

    pains_matches = catalog.GetMatches(mol)
    pains_score = 1.0 if len(pains_matches) == 0 else 0.0

    return {
        "Lipinski": lipinski_score,
        "Veber": veber_score,
        "PAINS": pains_score
    }
lipinski_vals = np.array([compute_scores(sm)['Lipinski'] for sm in SMILES])
print('Lipinski: ', round(lipinski_vals.mean(), 3), round(lipinski_vals.std(), 3))

veber_vals = np.array([compute_scores(sm)['Veber'] for sm in SMILES])
print('Veber: ', round(veber_vals.mean(), 3), round(veber_vals.std(), 3))

pains_vals = np.array([compute_scores(sm)['PAINS'] for sm in SMILES])
print('PAINS: ', round(pains_vals.mean(), 3), round(pains_vals.std(), 3))