import pubchempy as pcp
from toolset.call_gpt import gpt_api

def get_smiles_from_name(molecule_name: str) -> str:
    """
    Given a chemical name, return the canonical SMILES string.
    
    Args:
        molecule_name (str): Common or IUPAC name of the compound.
        
    Returns:
        str: SMILES string if found, otherwise a message saying not found.
    """
    try:
        # Search PubChem by name
        compounds = pcp.get_compounds(molecule_name, 'name')
        
        if not compounds:
            return None
        
        # Return canonical SMILES of the first compound
        return compounds[0].connectivity_smiles
    
    except Exception as e:
        return None

def name2smiles(molecule_name: str) -> str:
    smiles = get_smiles_from_name(molecule_name)
    if smiles is not None:
        return smiles
    else:
        try: 
            res = gpt_api(f'Find pubchem CID of {molecule_name}, return the CID only!')
            try:
                cid = int(res)
            except:
                cid = int(gpt_api(f'Extract the pubchem CID from this text: {res}, return only the number!'))
        except:
            try: 
                res = gpt_api(f'Find pubchem CID of {molecule_name}, return the CID only!')
                try:
                    cid = int(res)
                except:
                    cid = int(gpt_api(f'Extract the pubchem CID from this text: {res}, return only the number!'))
            except:
                try: 
                    res = gpt_api(f'Find pubchem CID of {molecule_name}, return the CID only!')
                    try:
                        cid = int(res)
                    except:
                        cid = int(gpt_api(f'Extract the pubchem CID from this text: {res}, return only the number!'))
                except:
                    cid = None
    if cid is not None:
        try: return pcp.Compound.from_cid(cid).connectivity_smiles
        except: return None
    else:
        return None