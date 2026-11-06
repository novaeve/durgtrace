from rdkit import DataStructs
from rdkit.ML.Cluster import Butina
from rdkit import RDLogger, Chem
from rdkit.Chem import AllChem
from tqdm import tqdm
RDLogger.DisableLog('rdApp.*')

def compute_distance_matrix(fps):
    dists = []
    for i in tqdm(range(1, len(fps))):
        sims = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
        dists.extend([1 - x for x in sims])
    return dists

def run_butina(fps, cutoff, dists):
    clusters = Butina.ClusterData(
        dists,
        len(fps),
        cutoff,
        isDistData=True
    )
    return clusters

def Butina_clustering(smiles_list, cutoff=0.75, radius=2, nBits=2048):
    valid_idx, fps = [], []
    for i, s in enumerate(tqdm(smiles_list, desc='Running Butina clustering: ')):
        try:
            mol = Chem.MolFromSmiles(s)
            if mol is not None:
                valid_idx.append(i)
                fps.append(AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=nBits))
        except:
            pass
    dists = compute_distance_matrix(fps)
    clusters = run_butina(fps, cutoff=cutoff, dists=dists)
    return clusters, valid_idx