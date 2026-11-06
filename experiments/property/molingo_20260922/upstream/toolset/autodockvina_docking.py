from toolset.uniprotID2name import uniprotID2name
from toolset.download_protein_rcsb import download_protein_rcsb
from toolset.download_protein_complex_rcsb import download_protein_complex_rcsb
from toolset.autodockvina_w_ligand import autodockvina_w_ligand
from toolset.autodockvina_wo_ligand import autodockvina_wo_ligand
from toolset.call_gpt import gpt_api
from ast import literal_eval


def autodockvina_docking(uniprot_id, smiles, sbdd=True, contact_threshold=7.0, max_hotspots=5):
    name = uniprotID2name(uniprot_id)
    try:
        results = download_protein_complex_rcsb(uniprot_id, name)
        if results['ligand_id'] is None:
            ligand_id = literal_eval(gpt_api(f'Go to this webpage: https://www.rcsb.org/structure/{results['pdb_id']}, small molecule section, and find the first ligand ID. Return result in this template:\n ```json\n{{"ligand_id": <result>}}\n```.').split('```json')[1].split('```')[0])['ligand_id']
            results['ligand_id'] = ligand_id
        r = autodockvina_w_ligand(results['pdb_id'], results['ligand_id'], smiles, sbdd=sbdd, contact_threshold=contact_threshold, max_hotspots=max_hotspots)
        return name, r
    except:
        try:
            results = download_protein_rcsb(uniprot_id, name)
            r = autodockvina_wo_ligand(results['pdb_id'], smiles, sbdd=sbdd, contact_threshold=contact_threshold, max_hotspots=max_hotspots)
            return name, r
        except:
            print(f'Failed to find protein {name} (Uniprot ID: {uniprot_id}) on RCSB.')
            return None
        
def docking_profile(smiles, protein_targets):
    ref_docking_scores = {}
    if len(protein_targets) > 0:
        for i in protein_targets.keys():
            ref_docking_scores[i] = autodockvina_docking(smiles=smiles, uniprot_id=i)
    else:
        print('No protein targets found!')
    return ref_docking_scores

if __name__ == '__main__':
    smiles = 'CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5'
    uniprot_id = 'P17081'
    docking_score = autodockvina_docking(uniprot_id, smiles)
    print(f'Docking score of {uniprot_id} and {smiles} is {docking_score}')