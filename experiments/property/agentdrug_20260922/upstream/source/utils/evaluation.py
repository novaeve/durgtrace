import tqdm
import numpy as np
import pandas as pd

from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import Descriptors
from rdkit.Chem import DataStructs

task2thres = {
    "LogP+" : [[0], [0.5]],
    "LogP-" : [[0], [0.5]],
    "TPSA+" : [[0], [10]],
    "TPSA-" : [[0], [10]],
    "HBD+"  : [[0], [1]],
    "HBD-"  : [[0], [1]],
    "HBA+"  : [[0], [1]],
    "HBA-"  : [[0], [1]],
    "QED+"  : [[0], [0.1]],
    "QED-"  : [[0], [0.1]],
}
task2prop = {
    "LogP+" : "MolLogP",
    "LogP-" : "MolLogP",
    "TPSA+" : "TPSA",
    "TPSA-" : "TPSA",
    "HBD+"  : "NumHDonors",
    "HBD-"  : "NumHDonors",
    "HBA+"  : "NumHAcceptors",
    "HBA-"  : "NumHAcceptors",
    "QED+"  : "qed",
    "QED-"  : "qed",
}
prop2func = {}
for prop, func in [(n, func) for n, func in Descriptors.descList if n.split("_")[-1] in list(set(task2prop.values()))]:
    prop2func[prop] = func
task2func = {k:prop2func[task2prop[k]] for k in task2prop.keys()}

def get_scores_generation(eval_outputs, path, data, hit_thres=0):
    df = pd.concat([pd.DataFrame(d) for d in eval_outputs])
    df.to_csv(path, index=False)

    prop = data.split("/")[-1]
    validities = []
    hits = []
    hit5s = []
    Morgan_sims = []
    if "single" in data:
        for pred, label in tqdm.tqdm(zip(df['pred'].values.tolist(), df['label'].values.tolist())):
            try:
                mol_pred, mol_label = Chem.MolFromSmiles(pred), Chem.MolFromSmiles(label)
                validities.append(1)

                sim = DataStructs.TanimotoSimilarity(AllChem.GetMorganFingerprint(mol_pred, 2), AllChem.GetMorganFingerprint(mol_label, 2))
                Morgan_sims.append(sim)

                prop_pred, prop_label = task2func[prop](mol_pred), task2func[prop](mol_label)
                if prop == "LogP+":
                    hits.append(prop_pred > prop_label + task2thres[prop][hit_thres][0])
                    hit5s.append(prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                if prop == "LogP-":
                    hits.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                    hit5s.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                if prop == "TPSA+":
                    hits.append(prop_pred > prop_label + task2thres[prop][hit_thres][0])
                    hit5s.append(prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                if prop == "TPSA-":
                    hits.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                    hit5s.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                if prop == "HBD+":
                    hits.append(prop_pred > prop_label + task2thres[prop][hit_thres][0])
                    hit5s.append(prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                if prop == "HBD-":
                    hits.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                    hit5s.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                if prop == "HBA+":
                    hits.append(prop_pred > prop_label + task2thres[prop][hit_thres][0])
                    hit5s.append(prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                if prop == "HBA-":
                    hits.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                    hit5s.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                if prop == "QED+":
                    hits.append(prop_pred > prop_label + task2thres[prop][hit_thres][0])
                    hit5s.append(prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                if prop == "QED-":
                    hits.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                    hit5s.append(prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
            except:
                validities.append(0)
    if "multi" in data:
        logp, prop = prop[:5], prop[5:]
        for pred, label in tqdm.tqdm(zip(preds, labels)):
            try:
                mol_pred, mol_label = Chem.MolFromSmiles(pred), Chem.MolFromSmiles(label)
                validities.append(1)

                sim = DataStructs.TanimotoSimilarity(AllChem.GetMorganFingerprint(mol_pred, 2), AllChem.GetMorganFingerprint(mol_label, 2))
                Morgan_sims.append(sim)

                logp_pred, logp_label, prop_pred, prop_label = task2func[logp](mol_pred), task2func[logp](mol_label), task2func[prop](mol_pred), task2func[prop](mol_label)
                if logp == "LogP+":
                    if prop == "TPSA+":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "TPSA-":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                    if prop == "HBD+":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "HBD-":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                    if prop == "HBA+":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "HBA-":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                    if prop == "QED+":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "QED-":
                        hits.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred > logp_label + task2thres[logp][hit_thres][0] and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                if logp == "LogP-":
                    if prop == "TPSA+":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "TPSA-":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                    if prop == "HBD+":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "HBD-":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                    if prop == "HBA+":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "HBA-":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
                    if prop == "QED+":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0])
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred > prop_label + task2thres[prop][hit_thres][0] and sim >= 0.5)
                    if prop == "QED-":
                        hits.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label)
                        hit5s.append(logp_pred + task2thres[logp][hit_thres][0] < logp_label and prop_pred + task2thres[prop][hit_thres][0] < prop_label and sim >= 0.5)
            except:
                validities.append(0)

    return 99.99*sum(hits)/len(validities), 99.99*sum(hit5s)/len(validities), 99.99*np.mean(Morgan_sims), 99.99*sum(validities)/len(validities)

eval_funcs = {
    'generation': get_scores_generation,
}