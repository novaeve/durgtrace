import torch
from toolset.admet_inference import admet_inference
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def PredictAMES(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='AMES', device=device, ckpt_path='model_weights'))

def PredictDILI(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

def PredicthERG(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='hERG', device=device, ckpt_path='model_weights'))

def PredictBBBP(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='BBBP', device=device, ckpt_path='model_weights'))

def PredictPgp(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='Pgp', device=device, ckpt_path='model_weights'))

# def PredictCYP3A4(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='CYP3A4', device=device, ckpt_path='model_weights'))

# def PredictCYP2D6(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

# def PredictCYP2C9(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

# def PredictCYP2C19(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

def PredictHIA(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='HIA', device=device, ckpt_path='model_weights'))

def PredictBioavailability(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]
    return list(admet_inference(smiles, name='Bioavailability', device=device, ckpt_path='model_weights'))

# def PredictLipophilicity(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

# def PredictSolubility(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

# def PredictPPBR(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

# def PredictHalflife(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

# def PredictClearance(smiles):
#     if not isinstance(smiles, list):
#         smiles = [smiles]
#     return list(admet_inference(smiles, name='DILI', device=device, ckpt_path='model_weights'))

def ADMET_Profile(smiles):
    if not isinstance(smiles, list):
        smiles = [smiles]

    d = {}
    for smi in smiles:
        try:
            profile = {
                'AMES': PredictAMES(smi)[0],
                'DILI': PredictDILI(smi)[0],
                'hERG': PredicthERG(smi)[0],
                'BBBP': PredictBBBP(smi)[0],
                'Pgp': PredictPgp(smi)[0],
                'HIA': PredictHIA(smi)[0],
            }
            d[smi] = profile
        except:
            print(f"Failed to predict ADMET properties for {smi}")
    return d

def ADMET_based_scoring(scores, BBBP=True, main_task=None):
    """
    scores: {'AMES': prob, 'DILI': prob, 'hERG': prob, 'BBBP': prob, 'Pgp': prob, 'HIA': prob}
    """ 
    
    if BBBP: max_val = 2
    else: max_val = 1
    if main_task is None:
        if BBBP: w = 1
        else: w = -1
        return - scores['AMES'] - scores['DILI'] - scores['hERG'] - scores['Pgp'] + scores['HIA'] + w*scores['BBBP'], max_val
    else:
        tasks = list(scores.keys())
        assert main_task in tasks, f'task must be in {tasks}'
        if main_task == 'HIA':
            return scores['HIA'], max_val
        elif main_task == 'BBBP':
            if BBBP: return scores['BBBP'], max_val
            else: return - scores['BBBP'], max_val
        else: # AMES, DILI, hERG, Pgp
            return - scores[main_task], max_val