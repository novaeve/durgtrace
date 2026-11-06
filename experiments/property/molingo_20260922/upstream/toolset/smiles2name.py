import pubchempy as pcp

def smiles2name(smiles: str) -> str:
    """
    Given a SMILES string, return the common name of the compound.
    
    Args:
        smiles (str): SMILES string of the compound.
        
    Returns:
        str: Common name if found, otherwise a message saying not found.
    """
    try:
        # Search for compound by SMILES
        compounds = pcp.get_compounds(smiles, 'smiles')
        
        if not compounds:
            return None
        
        # Return the common name if available
        compound = compounds[0]
        if compound.iupac_name:
            return compound.iupac_name
        elif compound.synonyms:
            # Return the first synonym as the common name
            return compound.synonyms[0]
        else:
            return None
    
    except Exception as e:
        return f"Error: {e}"
