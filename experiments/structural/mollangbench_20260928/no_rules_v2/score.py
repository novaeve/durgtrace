"""Offline-only official canonical-SMILES exact match evaluation."""
from pathlib import Path
import argparse,collections,contextlib,io,json,re
from rdkit import Chem,RDLogger
from transport import functions,dump
RDLogger.DisableLog('rdApp.*')
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'upstream/MolLangBench-main/scripts/evaluate_results.py'
ns={'re':re,'Chem':Chem,'Optional':__import__('typing').Optional}
functions(SOURCE,['canonicalize_smiles','parse_smiles_from_output'],ns)
canonical=ns['canonicalize_smiles'];parse=ns['parse_smiles_from_output']

def score(stage,method='deepseek'):
 answers=json.loads((ROOT/'data/answers.json').read_text());groups={};scored=[]
 for p in (ROOT/'runs'/stage/method).glob('*/result.json'):
  r=json.loads(p.read_text())
  prediction=parse({'body':{'choices':[{'message':{'content':r['output']}}]}})
  pred=canonical(prediction);gold=canonical(answers[r['id']])
  # Official parser's empty string is RDKit's zero-atom molecule and counts as valid.
  # Preserve published evaluator behavior; separately report nonempty chemical validity.
  row={'id':r['id'],'task':r['task'],'split':r['split'],'prediction':prediction,'valid_official':pred is not None,'valid_nonempty':bool(pred),'success':pred is not None and pred==gold,'runtime_status':r['status']}
  scored.append(row)
  for key in [r['task'],r['task']+'/'+r['split']]:
   g=groups.setdefault(key,collections.Counter());g['processed']+=1;g['success']+=row['success'];g['valid_official']+=row['valid_official'];g['valid_nonempty']+=row['valid_nonempty'];g['runtime_errors']+=r['status']!='complete'
 for key,g in groups.items():g['expected']=400 if '/' not in key else 200;g['accuracy_processed']=g['success']/g['processed']
 result={'stage':stage,'method':method,'groups':groups,'scored_rows':scored}
 dump(ROOT/'runs'/stage/method/'scores.json',result)
 print(json.dumps({'groups':groups}),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);ap.add_argument('--method',choices=['deepseek','chatdrug','agentdrug'],default='deepseek');a=ap.parse_args();score(a.stage,a.method)
