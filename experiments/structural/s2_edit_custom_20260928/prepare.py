"""Freeze locally audited upstream files; produce a narrow task-predicate patch."""
from pathlib import Path
import ast, hashlib, json, shutil
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent
(ROOT/'source').mkdir(exist_ok=True)
files={
 's2_properties.py':OUT/'molopt-audit-20260920/repos/S2-TOMG-Bench/utils/evaluation.py',
 's2_evaluate.py':OUT/'molopt-audit-20260920/repos/S2-TOMG-Bench/evaluate.py',
 'chatdrug_main.py':OUT/'molopt-audit-20260920/repos/ChatDrug/main_ChatDrug.py',
 'chatdrug_utils.py':OUT/'molopt-audit-20260920/repos/ChatDrug/utils.py',
 'chatdrug_parser.py':OUT/'molopt-audit-20260920/repos/ChatDrug/ChatDrug/task_and_evaluation/small_molecule_editing.py',
 'agentdrug_core.py':OUT/'agentdrug-20260922/core_fixed.py',
 'agentdrug_core_original.py':OUT/'agentdrug-20260922/core_original.py',
}
manifest={}
for name,path in files.items():
 shutil.copyfile(path,ROOT/'source'/name)
 manifest[name]={'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
code=(ROOT/'source/agentdrug_core.py').read_text(encoding='utf-8')
start=code.index('                    input_mol = Chem.MolFromSmiles')
end=code.index('                    if hit:',start)
code=code[:start]+'''                    output_mol = Chem.MolFromSmiles(output["pred"][0])
                    hit, DB, property_feedback = s2_feedback(output["pred"][0], test_dataset)
'''+code[end:]
(ROOT/'agentdrug_s2_core.py').write_text(code,encoding='utf-8')
# Reuse only transport, not the PMO ledger or search protocol.
transport=ast.parse((OUT/'pmo-1k-20260924/pmo_common.py').read_text(encoding='utf-8'))
names={'dump','sha','functions','APIError','LongTruncation','long_truncation','Relay'}
body=[node for node in transport.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names]
text='import ast, hashlib, json, pathlib, time\nimport requests\nMODEL="deepseek-v4.1-flash"\n'+ast.unparse(ast.Module(body=body,type_ignores=[]))+'\n'
(ROOT/'transport.py').write_text(text,encoding='utf-8')
(ROOT/'source/manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print('Frozen',len(files),'source files; patched only AgentDrug property-feedback block.')
