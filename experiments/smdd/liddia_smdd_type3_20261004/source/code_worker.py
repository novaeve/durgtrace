"""Execute LIDDIA CODE in an OS sandbox with no network or model weights."""
from pathlib import Path
import ast
import json
import pandas as pd
import numpy as np
from typing import Dict

source=Path('/work/code.py').read_text()
tree=ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node,(ast.Import,ast.ImportFrom)):
        modules=[node.module] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names]
        rejected=[m for m in modules if not m or m.split('.')[0] not in {'pandas','numpy','rdkit','math','typing','collections','re'}]
        if rejected:
            raise ValueError('Unsupported CODE imports: '+str(rejected)+'. Use supplied SAScore/Similarity columns, or rdkit.Contrib.SA_Score.sascorer; os/sys/path modifications are unavailable.')
data={k:pd.DataFrame(v) for k,v in json.loads(Path('/work/input.json').read_text()).items()}
exec(compile(tree,'generated_code','exec'),globals())
result=_function(data)
if not isinstance(result,pd.DataFrame) or 'SMILES' not in result:
    raise ValueError('CODE must return a DataFrame with SMILES')
Path('/work/result.json').write_text(result.to_json(orient='records'))
