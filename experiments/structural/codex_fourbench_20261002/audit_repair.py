"""Preserve original runs; retry confirmed transport failure once and reparse dative bonds."""
import collections,json,re,os,time,hashlib
from pathlib import Path
import run,score

ROOT=run.ROOT
STAGE='infra_retry_20261005'
VIEW=ROOT/'review_20261005'
RETRY='s2_MolCustom_BondNum_0220'

def parse_fixed(text):
    tags=re.findall(r'<answer>\s*(.*?)\s*</answer>',text,re.S|re.I)
    if len(tags)!=1 or '<summary>' in text.lower():return None
    answer=tags[0].strip()
    if answer.startswith('<smiles>') and answer.endswith('</smiles>'):answer=answer[8:-9].strip()
    return answer if answer and not any(c.isspace() for c in answer) and '<' not in answer.replace('<-','') else None

def refresh():
    counts=collections.Counter();audit=[];originals={}
    for p in sorted((ROOT/'runs/full').glob('*/result.json')):
        original=json.loads(p.read_text());d=dict(original);originals[d['id']]=run.sha(p)
        reason=None
        if not d.get('candidate'):
            if d['status']=='complete':
                parsed=parse_fixed(d.get('output',''))
                if parsed:
                    d['candidate']=parsed;reason='parser_dative_bond_fixed'
                else:reason='no_complete_final_answer'
            elif d['status']=='timeout':reason='wall_timeout_3600s'
            else:reason='transport_disconnect' if d['id']==RETRY else 'needs_review'
            counts[reason]+=1
            audit.append({'id':d['id'],'reason':reason,'original_status':original['status'],'seconds':original.get('seconds')})
        retry=ROOT/'runs'/STAGE/d['id']/'result.json'
        if d['id']==RETRY and retry.exists():
            d=json.loads(retry.read_text());d['candidate']=parse_fixed(d.get('output','')) if d['status']=='complete' else None
            d['review_source']=str(retry)
        elif reason=='parser_dative_bond_fixed':d['review_source']='original output; only allow SMILES <- bonds'
        run.dump(VIEW/'runs/full'/d['id']/'result.json',d)
    run.dump(VIEW/'audit.json',{'updated':time.time(),'counts':dict(counts),'cases':audit,'retry_ids':[RETRY],'original_sha256':originals})
    score.ROOT=VIEW;score.main('full')
    assert all(run.sha(ROOT/'runs/full'/cid/'result.json')==sha for cid,sha in originals.items())
    print('REVIEW_COUNTS',dict(counts),flush=True)

if __name__=='__main__':
    assert parse_fixed('<answer>N<-[Cu+2]</answer>')=='N<-[Cu+2]'
    assert parse_fixed('<answer><bad>C</bad></answer>') is None
    assert parse_fixed('<answer>CC</answer><answer>CO</answer>') is None
    assert parse_fixed('<answer>CC') is None
    refresh()
    c=next(c for c in run.cases() if c['id']==RETRY)
    print('RETRY_START',RETRY,flush=True)
    run.execute(c,STAGE)
    refresh()
    print('REPAIR_COMPLETE',flush=True)
