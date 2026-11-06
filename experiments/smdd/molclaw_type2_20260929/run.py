from pathlib import Path
import argparse,ast,concurrent.futures,fcntl,http.server,json,os,shutil,subprocess,sys,threading,time,uuid
import requests,yaml
ROOT=Path(__file__).resolve().parent
MOL=Path('/data2/chenfuxin/molclaw_20260924')
SMDD=Path('/data2/chenfuxin/smdd_type2_transfer_20260929')
sys.path.insert(0,str(SMDD))
from agent_harness.obfuscate import obfuscate_task
from pharmacophore_3d import evaluate_3d_pharmacophore

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));tmp.replace(p)

def gateway():
    # Native SCP MCP HTTP transport; inject credentials on the host only.
    key=(MOL/'private/scp.env').read_text().strip().split('=',1)[1]
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def relay(self):
            if self.path!='/mcp':self.send_error(404);return
            body=self.rfile.read(int(self.headers.get('Content-Length','0')))
            headers={k:v for k,v in self.headers.items() if k.lower() not in ['host','content-length','connection','authorization','scp-hub-api-key','accept-encoding']}
            headers['SCP-HUB-API-KEY']=key
            try:
                res=requests.request(self.command,'https://scp.intern-ai.org.cn/api/v1/mcp/2/DrugSDA-Tool',data=body or None,headers=headers,stream=True,timeout=(25,300))
                self.send_response(res.status_code)
                for k,v in res.headers.items():
                    if k.lower() not in ['transfer-encoding','content-length','content-encoding','connection']:self.send_header(k,v)
                self.send_header('Connection','close');self.end_headers()
                for chunk in res.iter_content(chunk_size=1):
                    if chunk:self.wfile.write(chunk);self.wfile.flush()
                res.close();self.close_connection=True
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:
                self.close_connection=True
        do_POST=relay;do_GET=relay;do_DELETE=relay
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server

def sandbox(work):
    cmd=['bwrap','--die-with-parent','--new-session','--unshare-pid','--unshare-ipc','--unshare-uts']
    for path in ['/usr','/bin','/lib','/lib64','/etc']:
        if Path(path).exists():cmd+=['--ro-bind',path,path]
    cmd+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--dir','/root']
    for path in [MOL/'runtime',MOL/'isolated_env',Path('/data2/chenfuxin/chatdrug_generalization_20260920/venv'),Path('/opt/codex-node')]:
        cmd+=['--ro-bind',str(path),str(path)]
    cmd+=['--ro-bind','/usr/bin/python3.10','/data2/chenfuxin/smdd-boltz-env/bin/python']
    cmd+=['--bind',str(work),'/workspace','--chdir','/workspace','--clearenv',
          '--setenv','PATH',str(MOL/'isolated_env/bin')+':/usr/local/bin:/usr/bin:/bin',
          '--setenv','HOME','/workspace/.home','--setenv','VIRTUAL_ENV',str(MOL/'isolated_env'),
          '--setenv','CLAUDE_CONFIG_DIR','/workspace/.runtime',
          '--setenv','ANTHROPIC_BASE_URL','http://127.0.0.1:18745',
          '--setenv','ANTHROPIC_AUTH_TOKEN','local-molclaw-proxy',
          '--setenv','ANTHROPIC_MODEL','deepseek-v4.1-flash',
          '--setenv','ANTHROPIC_DEFAULT_HAIKU_MODEL','deepseek-v4.1-flash',
          '--setenv','ANTHROPIC_DEFAULT_SONNET_MODEL','deepseek-v4.1-flash',
          '--setenv','ANTHROPIC_DEFAULT_OPUS_MODEL','deepseek-v4.1-flash',
          '--setenv','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC','1',
          '--setenv','MAX_THINKING_TOKENS','0',
          '--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1']
    return cmd

def job(tid,port):
    control=ROOT/'control'/tid;control.mkdir(parents=True,exist_ok=True)
    if (control/'result.json').exists():return json.loads((control/'result.json').read_text())
    work=ROOT/'work'/tid
    if work.exists():raise RuntimeError('Unfinished attempt exists; archive before retry')
    work.mkdir(parents=True)
    public=Path(obfuscate_task(str(SMDD/'tasks'/tid),'task'))
    assert set(p.name for p in public.iterdir())=={'receptor.pdb'}
    shutil.copyfile(public/'receptor.pdb',work/'receptor.pdb')
    shutil.copytree(MOL/'source/MolClaw-main/skills',work/'.claude/skills')
    dump(work/'mcp.json',{'mcpServers':{'molclaw-scp':{'type':'http','url':f'http://127.0.0.1:{port}/mcp'}}})
    task=yaml.safe_load((SMDD/'tasks'/tid/'task.yaml').read_text())
    source=MOL/'source/MolClaw-main/molclaw_run/infer/claude_agent/run_claude.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='_build_prompt')
    ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
    prompt=ns['_build_prompt'](task['description'],'Write solution.csv with exactly three rows x,y,z,type and no header. Put the same final CSV inside <answer>...</answer>.','both','receptor.pdb')
    (control/'prompt.txt').write_text(prompt)
    cmd=sandbox(work)+[str(MOL/'runtime/node_modules/.bin/claude'),'--dangerously-skip-permissions','-p','--model','deepseek-v4.1-flash','--output-format','stream-json','--verbose','--mcp-config','/workspace/mcp.json','--strict-mcp-config']
    start=time.time();dump(control/'started.json',{'started':start,'command':cmd,'task':tid})
    with (control/'events.jsonl').open('w') as stdout,(control/'stderr.log').open('w') as stderr:
        proc=subprocess.run(cmd,input=prompt,text=True,stdout=stdout,stderr=stderr)
    elapsed=time.time()-start
    dump(control/'exit.json',{'returncode':proc.returncode,'started':start,'ended':time.time(),'seconds':elapsed})
    events=[]
    for line in (control/'events.jsonl').read_text().splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    final=next((e for e in reversed(events) if e.get('type')=='result'),{})
    result={'method':'molclaw','task':tid,'status':'complete' if proc.returncode==0 and not final.get('is_error') else 'error','seconds':elapsed,'num_turns':final.get('num_turns'),'usage':final.get('usage'),'native_subtype':final.get('subtype'),'submitted_file':(work/'solution.csv').exists()}
    if result['submitted_file']:shutil.copyfile(work/'solution.csv',control/'solution.csv')
    dump(control/'result.json',result)
    print(json.dumps(result),flush=True)
    return result

def score():
    rows=[]
    for p in (ROOT/'control').glob('*/result.json'):
        try:x=evaluate_3d_pharmacophore(str(p.parent/'solution.csv'),str(SMDD/'tasks'/p.parent.name/'ground_truth.json'))
        except Exception as e:x={'n_correct':0,'score':0,'error':type(e).__name__}
        x['task']=p.parent.name;dump(p.parent/'evaluation.json',x);rows.append(x)
    result={'processed':len(rows),'expected':25,'correct_points':sum(x['n_correct'] for x in rows),'point_denominator':75,'passed_tasks':sum(x['score']==1 for x in rows),'task_denominator':25,'rows':rows}
    dump(ROOT/'scores.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)

def main():
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['pilot','full','score','preflight']);args=a.parse_args()
    if args.stage=='score':score();return
    ids=[s.strip() for s in (SMDD/'task_list.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    assert len(ids)==25
    if args.stage=='preflight':
        w=ROOT/'preflight';w.mkdir(exist_ok=True)
        code='import os,rdkit; assert not os.path.exists("'+str(SMDD)+'/tasks"); assert not os.path.exists("'+str(MOL)+'/private"); assert "SCP_HUB_API_KEY" not in os.environ; print("isolated_runtime_ready")'
        subprocess.run(sandbox(w)+['python','-c',code],check=True);return
    with (ROOT/'run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.stage=='pilot':ids=ids[:1]
        else:assert json.loads((ROOT/'control'/ids[0]/'result.json').read_text())['status']=='complete'
        service=gateway()
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(job,i,service.server_address[1]) for i in ids]
                for f in concurrent.futures.as_completed(futures):f.result();score()
        finally:service.shutdown()
if __name__=='__main__':main()
