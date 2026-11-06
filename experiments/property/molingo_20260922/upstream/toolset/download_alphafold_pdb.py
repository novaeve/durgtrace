import requests
import os

def download_alphafold_pdb(uniprot_id, save_dir=None):
    filename = f"AF-{uniprot_id}-F1-model_v6.pdb"
    
    # If a save directory is specified, make sure it exists
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)
    else:
        filepath = filename
    
    url = f"https://alphafold.ebi.ac.uk/files/{filename}"
    response = requests.get(url)
    
    if response.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(response.content)
        print(f"Downloaded {filename} successfully at {filepath}!")
    else:
        print(f"Failed to download file. Status code: {response.status_code}")

if __name__ == "__main__":
    download_alphafold_pdb('M9PBH7', './temp')