import os
import requests
import json
from toolset.call_gpt import gpt_api
from ast import literal_eval


def gpt_fallback(uniprot_id: str, protein_name: str, cutoff: float = 3.5):
    """
    Uses GPT as fallback to find best X-ray protein–ligand complex.
    Guaranteed structured JSON output.
    """

    system_prompt = f"""
You are a structural bioinformatics assistant.

Your task is to search RCSB PDB and identify the best protein–ligand complex structure.

Rules:
- Only use X-ray diffraction structures.
- Resolution must be <= {cutoff} Å.
- Prefer lowest resolution available.
- Ignore water, ions, buffers, and crystallization artifacts.
- Only return biologically relevant ligands (small molecules > 150 Da).
- Do NOT return apo structures.
- Do NOT return protein-protein complexes.
"""

    user_prompt = f"""
Find the best experimentally solved protein–ligand complex structure for:

UniProt ID: {uniprot_id}
Protein name: {protein_name}

Selection criteria:
- Experimental method: X-ray diffraction
- Resolution ≤ {cutoff} Å
- Must contain a biologically relevant ligand
- Exclude solvents (HOH), ions (Na, Cl, Mg, Ca, etc.), sulfate, phosphate
- Ligand molecular weight should be >150 Da

Return result in this exact JSON template:
```json
{{
  "protein": "Glycogen synthase kinase-3 beta",
  "pdb_id": "1GNG",
  "resolution": 2.60,
  "ligand_id": "TRS",
  "ligand_name": "2-AMINO-2-HYDROXYMETHYL-PROPANE-1,3-DIOL"
}}
```

If no valid complex exists, return null values.
"""

    try:
        result = gpt_api(system_prompt + user_prompt)
        return literal_eval(result.split('```json')[1].split('```')[0])

    except Exception as e:
        print("GPT fallback failed:", str(e))
        return None



RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry/"
RCSB_NONPOLYMER_URL = "https://data.rcsb.org/rest/v1/core/nonpolymer_entity/"

def search_structures(uniprot_id, cutoff = 3.5):
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

    r = requests.post(RCSB_SEARCH_URL, json=query)
    r.raise_for_status()
    data = r.json()

    return [x["identifier"] for x in data.get("result_set", [])]


def is_valid_ligand(pdb_id, entity_id):
    ligand_data = requests.get(
        RCSB_NONPOLYMER_URL + f"{pdb_id}/{entity_id}"
    ).json()

    chem = ligand_data.get("chem_comp", {})

    chem_id = chem.get("id")
    chem_name = chem.get("name")
    formula_weight = chem.get("formula_weight", 0)

    # Skip solvents, ions, small junk
    skip_ids = {"HOH", "NA", "CL", "MG", "K", "CA", "SO4", "PO4"}

    if chem_id in skip_ids:
        return None

    # Skip very small molecules (<150 Da usually solvent/ion)
    if formula_weight and formula_weight < 150:
        return None

    return {
        "ligand_id": chem_id,
        "ligand_name": chem_name
    }


def get_best_complex_(uniprot_id, protein_name, cutoff=3.5):
    pdb_ids = search_structures(uniprot_id, cutoff)

    for pdb_id in pdb_ids:
        entry = requests.get(RCSB_ENTRY_URL + pdb_id).json()

        resolution = entry.get("rcsb_entry_info", {}).get(
            "resolution_combined", [None]
        )[0]

        nonpolymer_ids = entry.get(
            "rcsb_entry_container_identifiers", {}
        ).get("non_polymer_entity_ids", [])

        for entity_id in nonpolymer_ids:
            ligand = is_valid_ligand(pdb_id, entity_id)
            if ligand:
                return {
                    "protein": protein_name,
                    "pdb_id": pdb_id,
                    "resolution": resolution,
                    "ligand_id": ligand["ligand_id"],
                    "ligand_name": ligand["ligand_name"]
                }

    return None


def download_protein_complex_rcsb(uniprot_id, protein_name, cutoff=3.5):
    # try:
    #     result = get_best_complex_(uniprot_id=uniprot_id, protein_name=protein_name, cutoff=cutoff)
    # except:
    result = gpt_fallback(uniprot_id=uniprot_id, protein_name=protein_name, cutoff=cutoff)
    return result

if __name__ == "__main__":

    from uniprotID2name import uniprotID2name

    uniprot_id = 'P11474'
    name = uniprotID2name(uniprot_id)
    print(name)
    result = download_protein_complex_rcsb(uniprot_id=uniprot_id, protein_name=name)

    print(result)