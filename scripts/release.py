"""Inspect and verify the frozen release without invoking a model or a scientific server."""
from pathlib import Path
import argparse,ast,csv,hashlib,json,shlex,sys

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def bundles():return read('manifests/bundles.json')

def catalog():
    for b in bundles():print(f"{b['group']:12} {b['id']:55} {b['files']:5} files")

def verify():
    problems=[];sources=read('manifests/sources.json')
    for row in sources:
        p=ROOT/row['path']
        if not p.is_file():problems.append({'path':row['path'],'error':'missing'})
        elif hashlib.sha256(p.read_bytes()).hexdigest()!=row['release_sha256']:problems.append({'path':row['path'],'error':'hash_mismatch'})
    syntax=[];known_compatibility=[]
    compatibility={r['path']:r for r in read('manifests/python_compatibility.json')} if (ROOT/'manifests/python_compatibility.json').exists() else {}
    for p in ROOT.rglob('*.py'):
        try:ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
        except SyntaxError as e:
            label=p.relative_to(ROOT).as_posix();issue={'path':label,'line':e.lineno,'error':e.msg}
            expected=compatibility.get(label)
            if expected and tuple(sys.version_info[:2])<tuple(expected['minimum_python']) and hashlib.sha256(p.read_bytes()).hexdigest()==expected['sha256']:
                known_compatibility.append(dict(issue,reason=expected['reason'],minimum_python=expected['minimum_python']))
            else:syntax.append(issue)
    counts={prefix:len(list((ROOT/'benchmarks/smdd/tasks').glob(prefix+'*/task.yaml'))) for prefix in ['smdd_002_','smdd_003_','smdd_004_']}
    if list(counts.values())!=[25,52,340]:problems.append({'error':'task_count','actual':counts})
    tables=read('results/published/tables.json')['tables']
    for t in tables:
        if any(len(r)!=len(t['headers']) for r in t['rows']):problems.append({'error':'table_shape','id':t['id']})
    result={'ok':not problems and not syntax,'source_files':len(sources),'bundles':len(bundles()),'task_counts':counts,'published_tables':len(tables),'problems':problems,'syntax_errors':syntax,'known_python_compatibility':known_compatibility,'scope':'integrity and syntax under this interpreter; recorded unused upstream modules may require a newer Python; no model/API/GPU experiments executed'}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 1

def render_tables():
    out=ROOT/'results/generated';out.mkdir(exist_ok=True,parents=True)
    lines=['# Submitted numerical tables','','These tables render the reported values. They do not recompute experiments.','']
    def cell(x):return '—' if x is None else str(x).replace('\n',' ').replace('|',r'\|')
    for t in read('results/published/tables.json')['tables']:
        lines+=['## '+t['id'],'',t['note'],'','| '+' | '.join(map(cell,t['headers']))+' |','| '+' | '.join(['---']*len(t['headers']))+' |']
        lines+=['| '+' | '.join(map(cell,row))+' |' for row in t['rows']];lines+=['']
        with (out/(t['id']+'.csv')).open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(t['headers']);w.writerows(t['rows'])
    (out/'tables.md').write_text('\n'.join(lines),encoding='utf-8')
    print(out/'tables.md')

def plan(args):
    b=next((b for b in bundles() if b['id']==args.bundle),None)
    if not b:raise SystemExit('Unknown bundle; use catalog')
    entry=(ROOT/b['path']/args.entry).resolve()
    if not entry.is_relative_to((ROOT/b['path']).resolve()) or not entry.is_file():raise SystemExit('Entry must be an existing file inside this bundle')
    # A container preserves frozen absolute paths without editing scientific functions.
    aliases=read('configs/path_aliases.json')
    command=['docker','run','--rm','--gpus','all','--mount',f'type=bind,src={ROOT},dst=/release']
    for old,rel in aliases.items():
        if (ROOT/rel).is_dir():command+=['--mount',f'type=bind,src={ROOT/rel},dst={old}']
    external=[]
    if args.bindings:
        external=json.loads(Path(args.bindings).read_text(encoding='utf-8'))
        for binding in external:
            if not Path(binding['source']).exists():raise SystemExit('Missing external source: '+binding['source'])
            suffix=',readonly' if binding.get('readonly',True) else ''
            command+=['--mount',f"type=bind,src={binding['source']},dst={binding['target']}"+suffix]
    command+=['-w','/release/'+b['path'],args.image,'python',args.entry]+args.arguments
    print(json.dumps({'status':'plan_only_not_executed','bundle':args.bundle,'external_bindings':len(external),'command':command,'shell_command':shlex.join(command),'note':'Requires the matching original scientific image, model runtime, external assets and locally configured credentials. See docs/reproduction.md.'},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    for name in ['catalog','verify','tables']:sub.add_parser(name)
    q=sub.add_parser('plan');q.add_argument('bundle');q.add_argument('entry');q.add_argument('--image',required=True);q.add_argument('--bindings')
    a,extra=p.parse_known_args()
    if a.cmd!='plan' and extra:p.error('unrecognized arguments: '+' '.join(extra))
    a.arguments=extra[1:] if extra and extra[0]=='--' else extra
    if a.cmd=='catalog':catalog()
    elif a.cmd=='verify':return verify()
    elif a.cmd=='tables':render_tables()
    elif a.cmd=='plan':plan(a)
    return 0
if __name__=='__main__':sys.exit(main())
