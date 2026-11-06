import requests

def uniprotID2name(uniprot_id):
    """
    Fetch the protein's recommended name from UniProt given a UniProt ID.
    """
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
    response = requests.get(url)
    
    if response.status_code != 200:
        raise ValueError(f"Unable to fetch data for UniProt ID {uniprot_id}. Status code: {response.status_code}")
    
    data = response.json()
    
    try:
        protein_name = data['proteinDescription']['recommendedName']['fullName']['value']
        return protein_name
    except KeyError:
        # Fallback: if recommendedName missing, try the first submittedName
        try:
            protein_name = data['proteinDescription']['submissionNames'][0]['fullName']['value']
            return protein_name
        except (KeyError, IndexError):
            return None

if __name__ == '__main__':
    uniprot_id = "P69905"  # Hemoglobin subunit alpha
    name = uniprotID2name(uniprot_id)
    print(f"Protein name: {name}")