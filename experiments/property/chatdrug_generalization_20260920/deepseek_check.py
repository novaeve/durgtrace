"""Official DeepSeek adapter configuration; frozen molecular workflow unchanged."""
import argparse, json
from urllib.parse import urlsplit
import pilot as p

def config():
    values={}
    for line in (p.ROOT/'private/deepseek.env').read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            k,v=line.split('=',1);values[k.strip().removeprefix('export ')]=v.strip().strip('"').strip("'")
    assert urlsplit(values['ANTHROPIC_BASE_URL']).hostname=='api.deepseek.com'
    assert values.get('ANTHROPIC_API_KEY')
    values['ANTHROPIC_MODEL']='deepseek-flash'
    return values

def main():
    p.env_config=config
    parser=argparse.ArgumentParser()
    parser.add_argument('--pilot',action='store_true')
    args=parser.parse_args()
    stage='deepseek_pilot' if args.pilot else 'deepseek_smoke'
    out=p.ROOT/'runs'/stage
    out.mkdir(parents=True,exist_ok=True)
    cases=json.loads((p.ROOT/'prepared/cases.json').read_text())
    selected=[]
    for bench in ('ChatDrug','S2-mini'):
        for prop in ('LogP','QED'):
            for direction in ('higher','lower'):
                selected.append(next(c for c in cases if c['benchmark']==bench and c['property']==prop and c['direction']==direction))
    if args.pilot:selected=cases
    p.dump(out/'run_config.json',{'model':'deepseek-flash','provider':'official DeepSeek','protocol':'Anthropic-compatible streaming',
        'thinking':'disabled','effort':'low','temperature':0,'max_output_tokens':2048,'workers':1,
        'case_ids':[c['id'] for c in selected],'runner_sha256':p.sha(__file__),'workflow_sha256':p.sha(p.__file__),
        'manifest_sha256':p.sha(p.ROOT/'prepared/manifest.json')})
    db=p.pd.read_csv(p.ROOT/'prepared/retrieval.csv')
    errors=0
    for case in selected:
        result=p.run_case(case,db,out)
        errors+=result['status']=='error'
        if errors>=2:break
    summary=p.summarize(stage)
    if summary['completed_cases']!=len(selected):raise SystemExit(2)

if __name__=='__main__':main()
