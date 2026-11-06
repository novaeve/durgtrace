from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'local_deps'))
import pyarrow.parquet as pq
UP=ROOT/'upstream/MolLangBench-main'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
cases=[];answers={};manifest={'dataset':json.loads((ROOT/'data/revision.json').read_text()),'source_archive_sha256':sha(ROOT/'source.zip'),'files':{},'splits':{}}
for task in ['edit','generation']:
 template=(UP/'prompts'/('editing' if task=='edit' else task)/'prompt_smiles.txt').read_text().strip()
 for split in ['test','extended']:
  path=ROOT/'data'/f'{task}_{split}.parquet';table=pq.read_table(path)
  names=['original_smiles','edit_instructions','edited_smiles'] if task=='edit' else ['structure_description','smiles']
  rows=table.select(names).to_pylist();assert len(rows)==200
  manifest['files'][path.name]=sha(path);manifest['splits'][f'{task}/{split}']=len(rows)
  for i,row in enumerate(rows):
   ident=f'{task}_{split}_{i:03d}'
   fields={k:v for k,v in row.items() if k not in ['edited_smiles','smiles']}
   cases.append({'id':ident,'task':task,'split':split,'index':i,'prompt':template.format(**fields),**fields})
   answers[ident]=row['edited_smiles' if task=='edit' else 'smiles']
(ROOT/'data/cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'data/answers.json').write_text(json.dumps(answers,indent=2),encoding='utf-8')
shutil.copyfile(ROOT.parent/'s2-edit-custom-20260928/transport.py',ROOT/'transport.py')
manifest['public_cases_sha256']=sha(ROOT/'data/cases.json');manifest['answers_sha256']=sha(ROOT/'data/answers.json')
(ROOT/'data/experiment_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Prepared',len(cases),'public cases and isolated answer map; no canaries or images in prompts.')
