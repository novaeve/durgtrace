"""Native MolClaw on four frozen benchmarks. Gold is offline-only."""
import ast,collections,concurrent.futures,fcntl,hashlib,http.server,json,os,re,shutil,signal,subprocess,sys,threading,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
MOL=Path('/data2/chenfuxin/molclaw_20260924')
S2=Path('/data2/chenfuxin/s2_edit_custom_20260928')
LANG=Path('/data2/chenfuxin/mollangbench_20260928')
MODEL='deepseek-v4.1-flash'

def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2));tmp.replace(p)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def extract(path,names,ns):
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)

# Reuse the audited existing filesystem sandbox and host-side credential gateway.
extract(ROOT/'native_transport_source.py',['sandbox','gateway'],globals())
_base_sandbox=sandbox
def sandbox(work):
    return [x.replace('http://127.0.0.1:18745','http://127.0.0.1:18749') for x in _base_sandbox(work)]
extract(MOL/'source/MolClaw-main/molclaw_run/infer/claude_agent/run_claude.py',['_build_prompt'],globals())

def cases():
    sys.path.insert(0,str(S2))
    import benchmark
    rows=[]
    for c in benchmark.cases():
        rows.append({'id':'s2_'+c['id'],'bench':'S2_'+c['task'],'bucket':c['subtask'],'index':c['row_index'],'prompt':c['instruction'],'s2_case':c})
    for c in json.loads((LANG/'data/cases.json').read_text()):
        rows.append({'id':'lang_'+c['id'],'bench':'MolLang_'+c['task'],'bucket':c['split'],'index':c['index'],'prompt':c['prompt'],'source_id':c['id']})
    assert collections.Counter(r['bench'] for r in rows)=={'S2_MolEdit':1500,'S2_MolCustom':1500,'MolLang_edit':400,'MolLang_generation':400}
    return sorted(rows,key=lambda c:(c['index'],c['bench'],c['bucket']))

def parse(text):
    # Unique native submission only; never select an earlier trajectory candidate.
    tags=re.findall(r'<answer>\s*(.*?)\s*</answer>',text,re.S|re.I)
    if len(tags)!=1 or '<summary>' in text.lower():return None
    answer=tags[0].strip()
    if answer.startswith('<smiles>') and answer.endswith('</smiles>'):answer=answer[8:-9].strip()
    return answer if answer and not any(c.isspace() for c in answer) and '<' not in answer else None

def job(c,stage,port):
    control=ROOT/'runs'/stage/c['id'];control.mkdir(parents=True,exist_ok=True)
    if (control/'result.json').exists():return json.loads((control/'result.json').read_text())
    work=ROOT/'work'/stage/c['id']
    # Incomplete native episodes are not silently restarted.
    if (control/'started.json').exists():
        row={'id':c['id'],'bench':c['bench'],'bucket':c['bucket'],'status':'interrupted','candidate':None}
        dump(control/'result.json',row);return row
    work.mkdir(parents=True,exist_ok=True)
    shutil.copytree(MOL/'source/MolClaw-main/skills',work/'.claude/skills',dirs_exist_ok=True)
    dump(work/'mcp.json',{'mcpServers':{'molclaw-scp':{'type':'http','url':f'http://127.0.0.1:{port}/mcp'}}})
    query=c['prompt']
    # Sole format adaptation, retaining the full original chemical instructions.
    if c['bench'].startswith('MolLang_'):
        query=query.replace('<smiles>','<answer>').replace('</smiles>','</answer>')
    prompt=_build_prompt(query,'Submit exactly ONE final molecule as <answer>SMILES</answer>.','both',None)
    (control/'prompt.txt').write_text(prompt)
    command=sandbox(work)+[str(MOL/'runtime/node_modules/.bin/claude'),'--dangerously-skip-permissions','-p','--model',MODEL,'--output-format','stream-json','--verbose','--mcp-config','/workspace/mcp.json','--strict-mcp-config']
    started=time.time();dump(control/'started.json',{'time':started,'command':command})
    stalled=False
    with (control/'events.jsonl').open('w') as stdout,(control/'stderr.log').open('w') as stderr:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True,start_new_session=True)
        first=True
        while True:
            try:proc.communicate(input=prompt if first else None,timeout=20);break
            except subprocess.TimeoutExpired:
                first=False
                if time.time()-max(started,(control/'events.jsonl').stat().st_mtime)>1800:
                    stalled=True;os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    break
    events=[]
    for line in (control/'events.jsonl').read_text().splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    final=next((e for e in reversed(events) if e.get('type')=='result'),{})
    status='stalled' if stalled else ('complete' if proc.returncode==0 and final and not final.get('is_error') else 'error')
    text=final.get('result','')
    row={'id':c['id'],'bench':c['bench'],'bucket':c['bucket'],'status':status,'candidate':parse(text) if status=='complete' else None,'output':text,'returncode':proc.returncode,'usage':final.get('usage'),'num_turns':final.get('num_turns'),'subtype':final.get('subtype'),'seconds':time.time()-started}
    dump(control/'result.json',row)
    print(json.dumps({'id':c['id'],'status':status,'has_submission':row['candidate'] is not None}),flush=True)
    return row

def summary(stage,selected):
    rows=[json.loads(p.read_text()) for p in (ROOT/'runs'/stage).glob('*/result.json')]
    groups={}
    for bench,count in collections.Counter(c['bench'] for c in selected).items():
        rr=[r for r in rows if r['bench']==bench]
        groups[bench]={'expected':count,'processed':len(rr),'runtime_errors':sum(r['status']!='complete' for r in rr),'missing_submission':sum(not r.get('candidate') for r in rr)}
    result={'processed':len(rows),'expected':len(selected),'groups':groups,'updated':time.time()}
    dump(ROOT/'runs'/stage/'summary.json',result);return result

def main():
    stage=sys.argv[1];selected=cases()
    if stage=='pilot':selected=[c for c in selected if c['index']==0]
    with (ROOT/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        service=gateway()
        try:
            summary(stage,selected)
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                futures={pool.submit(job,c,stage,service.server_address[1]):c for c in selected}
                for f in concurrent.futures.as_completed(futures):f.result();summary(stage,selected)
        finally:service.shutdown()
    if stage=='pilot':
        rows=[json.loads(p.read_text()) for p in (ROOT/'runs'/stage).glob('*/result.json')]
        if any(r['status']!='complete' for r in rows):raise SystemExit('Pilot transport/runtime failure; full launch blocked')

if __name__=='__main__':main()
