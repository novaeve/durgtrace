import requests
from toolset.call_gpt import gpt_api
from ast import literal_eval

def gpt_fallback(uniprot_id: str, protein_name: str, cutoff: float = 3.5):
    """
    Uses GPT as fallback to find best X-ray protein structure (no ligand requirement).
    Guaranteed structured JSON output.
    """

    system_prompt = f"""
You are a structural bioinformatics assistant.

Your task is to search RCSB PDB and identify the best experimentally solved structure for a protein.

Rules:
- Only use X-ray diffraction structures.
- Resolution must be <= {cutoff} Å.
- Prefer lowest resolution available.
- Structure may be apo or holo.
- Do NOT return cryo-EM or NMR structures.
"""

    user_prompt = f"""
Find the best experimentally solved protein structure for:

UniProt ID: {uniprot_id}
Protein name: {protein_name}

Selection criteria:
- Experimental method: X-ray diffraction
- Resolution ≤ {cutoff} Å
- Prefer the lowest resolution available

Return result in this exact JSON format:
```json
{{
  "protein": "<protein_name>",
  "pdb_id": "<PDB ID>",
  "resolution": <float>,
  "experimental_method": "X-RAY DIFFRACTION"
}}
```
If no valid structure exists, return null values.
"""

    try:

        result = gpt_api(system_prompt + user_prompt)

        return literal_eval(result.split('```json')[1].split('```')[0])

    except Exception as e:
        print("GPT fallback failed:", str(e))
        return None

RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry/"

def search_best_protein_structure_(uniprot_id, cutoff=3.5):
    """
    Search RCSB for high-resolution (<= 2.5 Å)
    X-ray structures of a protein, ignoring ligands.
    Returns the PDB ID and resolution.
    """

    query = {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                        "operator": "exact_match",
                        "value": uniprot_id
                    }
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "exptl.method",
                        "operator": "exact_match",
                        "value": "X-RAY DIFFRACTION"
                    }
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entry_info.resolution_combined",
                        "operator": "less_or_equal",
                        "value": cutoff
                    }
                }
            ]
        },
        "return_type": "entry",
        "request_options": {
            "sort": [
                {
                    "sort_by": "rcsb_entry_info.resolution_combined",
                    "direction": "asc"
                }
            ]
        }
    }

    response = requests.post(RCSB_SEARCH_URL, json=query)
    response.raise_for_status()
    data = response.json()

    if "result_set" not in data or not data["result_set"]:
        return None

    # Return the PDB ID of the best (highest-resolution) structure
    pdb_id = data["result_set"][0]["identifier"]

    entry_data = requests.get(RCSB_ENTRY_URL + pdb_id).json()
    resolution = entry_data.get("rcsb_entry_info", {}).get(
        "resolution_combined", [None]
    )[0]

    return {"pdb_id": pdb_id, "resolution": resolution}

def download_protein_rcsb(uniprot_id, protein_name, cutoff=3.5):
    # try:
    #     result = search_best_protein_structure_(uniprot_id, cutoff=cutoff)
    # except:
    result = gpt_fallback(uniprot_id, protein_name, cutoff=cutoff)
    return result

# -----------------------------
# Example: DNA Topoisomerase 1
# -----------------------------
if __name__ == "__main__":
    from uniprotID2name import uniprotID2name
    uniprot_id = 'P23975'
    name = uniprotID2name(uniprot_id)
    result = download_protein_rcsb(uniprot_id, name, cutoff=3.5)
    print(result)