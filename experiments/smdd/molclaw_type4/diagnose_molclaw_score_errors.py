from pathlib import Path
import json, re, datetime
r=Path('/yimin/zlc/molclaw_type4_20261003')
print('TIME',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat())
for p in sorted((r/'evaluation/molclaw').glob('*/result.json')):
    d=json.loads(p.read_text())
    if d.get('status')!='errored':continue
    print('TASK',p.parent.name,'STEPS',[(s['name'],s['status']) for s in d['steps']])
    q=p.parent/'queue'
    print('QUEUE_FILES',[str(f.relative_to(q)) for f in q.rglob('*') if f.is_file() and len(f.relative_to(q).parts)<4][:50])
    for log in q.rglob('*'):
        if not log.is_file() or log.suffix not in ['.log','.json','.txt'] or log.stat().st_size>2_000_000:continue
        if log.suffix=='.json' and log.name not in ['result.json','status.json','request.json']:continue
        content=log.read_text(errors='replace')
        lines=content.splitlines()
        important=[(i,l) for i,l in enumerate(lines) if re.search(r'out of memory|Error|Exception|killed|failed|Traceback|CUDA|returncode|exit_code|Timeout|too many|Connection|No space|MSA server',l,re.I)]
        print('LOG',str(log.relative_to(p.parent)),'BYTES',log.stat().st_size)
        if important:
            indices=set()
            for i,l in important:
                indices.update(range(max(0,i-2),min(len(lines),i+4)))
            print('\n'.join(lines[i] for i in sorted(indices))[-5000:])
        else:print(content[-1200:])
    errors=p.parent/'errors'
    if errors.is_dir():
        for log in errors.iterdir():
            if log.is_file():print('ERROR_DETAIL',log.name,log.read_text(errors='replace')[-1200:])
