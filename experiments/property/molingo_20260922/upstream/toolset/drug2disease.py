from toolset.call_gpt import gpt_api
from ast import literal_eval

def drug2disease(molecule_name):
    prompt = (f'What condition or disease is {molecule_name} used to treat? In the conclusion, write the json dictionary. For example:\n'
    "```json\n"
    "{'Metformin': 'type 2 diabetes'}\n"
    "```")
    return literal_eval(gpt_api(prompt).split('```json')[1].split('```')[0])