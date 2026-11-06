from chembl_webresource_client.new_client import new_client
import pandas as pd

def protein2binders(uniprot_id, binding_threshold=1000):
    target = new_client.target
    activity = new_client.activity

    # 1. Map UniProt ID → ChEMBL target ID
    targets = target.filter(target_components__accession=uniprot_id)

    if len(targets) == 0:
        raise ValueError(f"No ChEMBL target found for UniProt ID {uniprot_id}")

    chembl_target_id = targets[0]['target_chembl_id']
    print(f"UniProt {uniprot_id} → ChEMBL target {chembl_target_id}")

    # 2. Query binding affinity data
    activities = activity.filter(
        target_chembl_id=chembl_target_id,
        assay_type='B'  # Binding assays only
    ).only([
        'molecule_chembl_id',
        'canonical_smiles',
        'standard_type',
        'standard_value',
        'standard_units',
        'standard_relation',
        'pchembl_value',
        'assay_chembl_id',
        'document_chembl_id'
    ])

    # 3. Convert to DataFrame
    df = pd.DataFrame(activities)

    df.dropna(subset=['standard_value', 'standard_units', 'standard_relation'], inplace=True)
    df = df[df['standard_units']=='nM']
    df = df[(df['standard_relation'] == '<') | (df['standard_relation'] == '=')]
    df['standard_value'] = df['standard_value'].astype(float)
    df = df[df['standard_value']<binding_threshold]
    df.reset_index(inplace=True)
    df.drop(columns=['index'], inplace=True)

    return df

# def protein2binders(uniprot_id, binding_threshold=1000):
#     target = new_client.target
#     activity = new_client.activity

#     # 1. Map UniProt ID
#     targets = target.filter(target_components__accession=uniprot_id)
#     if not targets:
#         raise ValueError(f"No ChEMBL target found for {uniprot_id}")
    
#     chembl_target_id = targets[0]['target_chembl_id']

#     # 2. Query with API-SIDE FILTERS
#     # This tells the server to only send back rows that already meet your criteria
#     activities = activity.filter(
#         target_chembl_id=chembl_target_id,
#         assay_type='B',
#         standard_units='nM',  # Filter on the server
#         pchembl_value__isnotnull=True # Only get rows with calculated affinity
#     ).only([
#         'molecule_chembl_id',
#         'canonical_smiles',
#         'pchembl_value',
#         'standard_value',
#         'standard_relation'
#     ])

#     # 3. Convert to list then DataFrame (More stable for large sets)
#     # We use a list comprehension to avoid the 500 error during DF construction
#     activity_list = []
#     try:
#         for act in activities:
#             activity_list.append(act)
#             if len(activity_list) > 2000: # Safety cap for very large targets
#                 break
#     except Exception as e:
#         print(f"Connection interrupted, processing gathered data: {e}")

#     df = pd.DataFrame(activity_list)

#     if df.empty:
#         return df

#     # 4. Clean up
#     df['standard_value'] = pd.to_numeric(df['standard_value'], errors='coerce')
#     df = df[df['standard_value'] < binding_threshold]
    
#     return df

if __name__ == '__main__':
    uniprot_id = "P05177"
    df = protein2binders(uniprot_id)

    print(df.head())
    print(f"\nTotal binding records: {len(df)}")