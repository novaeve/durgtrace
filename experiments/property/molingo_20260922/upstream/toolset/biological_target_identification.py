import json
from ast import literal_eval
import re
from toolset.call_gpt import gpt_api
from collections import Counter

# def literature_target_agent_gpt(disease, subtype=None, pathway=None, gene_mutation=None, max_papers=10):
#     """
#     GPT-driven pipeline to extract protein targets and agents.
#     Includes robust sanitization to prevent JSON decode errors.
#     """
#     added_txt = []
#     if subtype is not None:
#       added_txt.append(f"disease substype: {subtype}")
#     if pathway is not None:
#       added_txt.append(f"pathway: {pathway}")
#     if gene_mutation is not None:
#       added_txt.append(f"gen mutation: {gene_mutation}")
#     if len(added_txt) > 0:
#        added_txt = ', '.join(added_txt)
#        added_txt = f" ({added_txt})"
#     else:
#        added_txt = ''

#     prompt = f"""
#     You are a professional biomedical curator.
    
#     TASK:
#     1. Identify {max_papers} specific, high-impact research papers regarding therapeutic targets for "{disease}"{added_txt}. It's okay if you cannot find that number of papers. Make sure the papers are quality and relevant.
#     2. Extract the protein targets and the specific therapeutic agents (drugs/antibodies) mentioned.
#     3. Return ONLY a JSON object. No intro, no outro, no markdown formatting.
    
#     JSON STRUCTURE:
#     {{
#       "Paper Title": {{
#         "Protein Target Symbol": "Uniprot ID of the protein"
#       }}
#     }}
    
#     Example:
#     {{
#       "TNF-alpha inhibition in RA": {{
#         "TNF": "P01375",
#         "IL6R": "H0Y949"
#       }}
#     }}
#     """
    
#     try:
#         # 1. Call the API
#         response = gpt_api(prompt)
        
#         # 2. SANITIZE: Remove potential Markdown code blocks (```json ... ```)
#         # This regex looks for the first '{' and last '}' to isolate the JSON string
#         json_match = re.search(r'(\{.*\}|\[.*\])', response, re.DOTALL)
        
#         if json_match:
#             clean_json = json_match.group(0)
#             extracted_data = json.loads(clean_json)
#             targets = dict()
#             proteins_count = []
#             for v in extracted_data.values():
#                     targets = targets | v
#                     proteins_count.extend(list(v.keys()))

#             proteins_count = Counter(proteins_count)
#             targets = {k: {'Uniprot ID': v, 'count': proteins_count[k]} for k, v in targets.items()}
#             return targets
#         else:
#             print("⚠️ No JSON-like structure found in GPT response.")
#             return {}
            
#     except json.JSONDecodeError as je:
#         print(f"⚠️ JSON Parsing failed: {je}")
#         print("Raw response was:", response)
#         return {}
#     except Exception as e:
#         print(f"⚠️ Agent error: {e}")
#         return {}


# def biological_target_identification_(disease, subtype=None, pathway=None, gene_mutation=None, max_papers=10):
#   extracted_data = literature_target_agent_gpt(disease, subtype=subtype, pathway=pathway, gene_mutation=gene_mutation, max_papers=max_papers)
#   max_key = max(extracted_data, key=lambda k: extracted_data[k]['count'])
#   cnt = extracted_data[max_key]['count']
#   uniprot_id = extracted_data[max_key]['Uniprot ID']
#   return max_key, uniprot_id, cnt, extracted_data

# def biological_target_identification(disease, subtype=None, pathway=None, gene_mutation=None, max_papers=20):
#   cnt = 0
#   tries = 0
#   while cnt < 2:
#     name, uniprot_id, cnt, extracted_data = biological_target_identification_(disease, subtype=subtype, pathway=pathway, gene_mutation=gene_mutation, max_papers=max_papers)
#     tries += 1
#     if tries >= 5:
#         break
#   return name, uniprot_id, cnt, extracted_data



import json
from ast import literal_eval
from toolset.call_gpt import gpt_api
def literature_target_agent_gpt(disease, subtype=None, pathway=None, gene_mutation=None):
    """
    GPT-driven pipeline to extract protein targets and agents.
    Includes robust sanitization to prevent JSON decode errors.
    """
    added_txt = []
    if subtype is not None:
      added_txt.append(f"disease substype: {subtype}")
    if pathway is not None:
      added_txt.append(f"pathway: {pathway}")
    if gene_mutation is not None:
      added_txt.append(f"gen mutation: {gene_mutation}")
    if len(added_txt) > 0:
       added_txt = ', '.join(added_txt)
       added_txt = f" ({added_txt})"
    else:
       added_txt = ''

    prompt = f"""
You are a professional biomedical curator.

TASK:
What is the primary protein target of this disease: "{disease}"{added_txt}.
Extract the protein targets and one paper as a reference.
In the conclusion, include a python dictionary.

```python
{{
    "Protein Target Name": {{
    "Uniprot ID": [Uniprot ID of the protein],
    "Reference": [title of the reference paper]
    }}
}}
```
"""
    
    try:
        response = gpt_api(prompt)
        targets = literal_eval(response.split('```python')[1].split('```')[0])
        return targets
    except:
       return {}
    
def biological_target_identification_(disease, subtype=None, pathway=None, gene_mutation=None):
  extracted_data = literature_target_agent_gpt(disease, subtype=subtype, pathway=pathway, gene_mutation=gene_mutation)
  return extracted_data

def biological_target_identification(disease, subtype=None, pathway=None, gene_mutation=None):
    extracted_data = biological_target_identification_(disease=disease, subtype=subtype, pathway=pathway, gene_mutation=gene_mutation)
    cnt = 0
    while extracted_data is None:
        extracted_data = biological_target_identification_(disease=disease, subtype=subtype, pathway=pathway, gene_mutation=gene_mutation)
        cnt += 1
        if cnt == 3:
           break
    return extracted_data