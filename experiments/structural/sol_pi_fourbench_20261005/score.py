"""Offline scoring only; no results are supplied to native agents."""
import json,sys,re,collections
from pathlib import Path
from rdkit import Chem
from run import ROOT,S2,LANG,cases,dump,extract
sys.path.insert(0,str(S2))
import benchmark
ns={'Chem':Chem,'re':re,'Optional':__import__('typing').Optional}
extract(LANG/'upstream/MolLangBench-main/scripts/evaluate_results.py',['canonicalize_smiles','parse_smiles_from_output'],ns)

def main(stage):
    selected=cases()
    if stage=='pilot':selected=[c for c in selected if c['index']==0]
    answers=json.loads((LANG/'data/answers.json').read_text())
    groups={};scored=[]
    for c in selected:
        g=groups.setdefault(c['bench'],collections.Counter());g['expected']+=1
        p=ROOT/'runs'/stage/c['id']/'result.json'
        if not p.exists():continue
        r=json.loads(p.read_text());candidate=r.get('candidate')
        if c['bench'].startswith('S2_'):s=benchmark.evaluate(c['s2_case'],candidate)
        else:
            official=ns['parse_smiles_from_output']('<smiles>'+candidate+'</smiles>' if candidate else '')
            canon=ns['canonicalize_smiles'](official);gold=ns['canonicalize_smiles'](answers[c['source_id']])
            s={'success':bool(canon) and canon==gold,'valid':bool(canon),'valid_official':canon is not None}
        g['processed']+=1;g['success']+=s['success'];g['valid']+=s['valid'];g['runtime_errors']+=r['status']!='complete'
        if 'valid_official' in s:g['valid_official']+=s['valid_official']
        if 'similarity' in s:g['similarity_sum']+=s['similarity'];g['similarity_count']+=1
        scored.append({'id':c['id'],'bench':c['bench'],'bucket':c['bucket'],'score':s})
    for g in groups.values():
        g['success_rate_full_denominator']=g['success']/g['expected']
        g['valid_rate_full_denominator']=g['valid']/g['expected']
        if g['similarity_count']:g['mean_valid_similarity']=g['similarity_sum']/g['similarity_count']
    dump(ROOT/'runs'/stage/'scores.json',{'groups':groups,'rows':scored})
    print(json.dumps(groups))
if __name__=='__main__':main(sys.argv[1])
