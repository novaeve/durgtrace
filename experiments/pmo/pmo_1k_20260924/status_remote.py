"""Read-only concise live status, including in-flight oracle records."""
import collections,json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parent
report={'time':time.time()}
for stage in ['pilot','full']:
    groups={};errors=[]
    for p in (ROOT/'runs'/stage).glob('*/*/*/config.json'):
        c=json.loads(p.read_text());d=p.parent
        r=json.loads((d/'result.json').read_text()) if (d/'result.json').exists() else (json.loads((d/'progress.json').read_text()) if (d/'progress.json').exists() else {'status':'queued'})
        n=len((d/'oracle.jsonl').read_text().splitlines()) if (d/'oracle.jsonl').exists() else 0
        g=groups.setdefault(c['method'],collections.Counter());g[r['status']]+=1;g['oracle_calls']+=n
        if r['status'] not in ['running','queued','complete']:
            errors.append({'method':c['method'],'task':c['task'],'seed':c['seed'],'status':r['status'],'error':r.get('error')})
    report[stage]={'groups':groups,'errors':errors}
print(json.dumps(report,ensure_ascii=False,indent=2))
