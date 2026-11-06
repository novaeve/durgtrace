import re

def get_validity_feedback(smiles, code_executor_agent):
    code_output = """
    ```python
from rdkit import Chem

mol = Chem.MolFromSmiles("{}")
if mol is not None:
    print("The modified molecule is chemically valid.")
else:
    print("The modified molecule is not chemically valid.")
    ```
    """.format(smiles)
    obs = code_executor_agent.generate_reply(messages=[{"role": "user", "content": code_output}]).split("Code output: ")[-1].strip()
    obs = re.sub(r'\[\d{2}:\d{2}:\d{2}\] ', '', obs)
    return obs