import ast,collections,concurrent.futures,fcntl,hashlib,json,os,re,subprocess,sys,time,traceback,urllib.request,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent;B=ROOT/'bundle'
def dump(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2));t.replace(p)
def score(*args):return {}
tree=ast.parse((ROOT/'claw_native_original.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case')
exec(compile(ast.Module(body=[node],type_ignores=[]),'frozen_native_run_case','exec'))
CASES={c['id']:c for c in json.loads((ROOT/'cases.json').read_text())}
def collect_existing(cid):
 out=ROOT/'raw_results'/(cid+'.json');native_dir=ROOT/'native/MolClaw/full'/cid
 if out.exists():return True
 if not (native_dir/'result.json').exists():
  if not (native_dir/'events.jsonl').exists():return False
  terminal=[]
  for line in (native_dir/'events.jsonl').read_text().splitlines():
   try:e=json.loads(line)
   except ValueError:continue
   if e.get('type')=='result':terminal.append(e)
  if not terminal:return False
  # Original wrapper may have been killed after the native CLI finished; parse
  # its preserved terminal response without issuing another inference call.
  ns=dict(globals());ns['subprocess']=types.SimpleNamespace(run=lambda *args,**kw:types.SimpleNamespace(returncode=0))
  exec(compile(ast.Module(body=[node],type_ignores=[]),'recover_preserved_native_final','exec'),ns)
  ns['run_case'](CASES[cid],'full')
 row=json.loads((native_dir/'result.json').read_text());c=CASES[cid]
 assert row['case']==c and c['instruction'] in (native_dir/'prompt.txt').read_text()
 events=[]
 for line in (native_dir/'events.jsonl').read_text().splitlines():
  try:events.append(json.loads(line))
  except ValueError:pass
 init=next((e for e in events if e.get('type')=='system' and e.get('subtype')=='init'),None)
 if init:assert init.get('model')=='deepseek-v4.1-flash'
 row.update(finished=time.time(),execution_host=json.loads((ROOT/'control.json').read_text())['host'],collected_from_preserved_native_result=True,runtime_init={k:init.get(k) for k in ['model','tools','skills','claude_code_version','permissionMode']} if init else None)
 dump(out,row);return True
def execute(cid):
 with (ROOT/'locks'/ (cid+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);out=ROOT/'raw_results'/(cid+'.json')
  if out.exists():return
  c=CASES[cid];dump(ROOT/'started'/(cid+'.json'),dict(id=cid,time=time.time(),host=json.loads((ROOT/'control.json').read_text())['host']))
  run_case(c,'full');native_dir=ROOT/'native/MolClaw/full'/cid
  assert c['instruction'] in (native_dir/'prompt.txt').read_text()
  events=[]
  for line in (native_dir/'events.jsonl').read_text().splitlines():
   try:events.append(json.loads(line))
   except ValueError:pass
  init=next((e for e in events if e.get('type')=='system' and e.get('subtype')=='init'),None)
  if init:assert init.get('model')=='deepseek-v4.1-flash',init.get('model')
  row=json.loads((native_dir/'result.json').read_text());row.update(case=c,finished=time.time(),execution_host=json.loads((ROOT/'control.json').read_text())['host'],runtime_init={k:init.get(k) for k in ['model','tools','skills','claude_code_version','permissionMode']} if init else None)
  dump(out,row)
def main():
 for n in ['locks','started','raw_results']: (ROOT/n).mkdir(exist_ok=True)
 with (ROOT/'worker_v2.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  cfg=json.loads((ROOT/'control.json').read_text());ids=json.loads((ROOT/'assigned_ids.json').read_text());assert len(ids)==len(set(ids)) and all(i in CASES for i in ids)
  assert hashlib.sha256((ROOT/'cases.json').read_bytes()).hexdigest()==json.loads((ROOT/'runtime_validation.json').read_text())['cases_sha256']
  legacy=json.loads((ROOT/'draining_ids.json').read_text()) if (ROOT/'draining_ids.json').exists() else []
  pending=collections.deque(i for i in ids if i not in legacy and not (ROOT/'raw_results'/(i+'.json')).exists());active={};last=0;lastscale=time.time();pos=(ROOT/'proxy.log').stat().st_size;errors=0;last_error=0
  with concurrent.futures.ThreadPoolExecutor(cfg['maximum']) as pool:
   while pending or active or any(not (ROOT/'raw_results'/(i+'.json')).exists() for i in legacy):
    cfg=json.loads((ROOT/'control.json').read_text());limit=cfg['workers'];proxy_ok=False
    try:proxy_ok=urllib.request.urlopen('http://127.0.0.1:49493/health/liveliness',timeout=3).status==200
    except Exception:pass
    legacy_active=sum(not collect_existing(cid) for cid in legacy)
    while pending and len(active)<max(0,limit-legacy_active) and proxy_ok and not (ROOT/'pause_generation.request').exists():
     cid=pending.popleft();active[pool.submit(execute,cid)]=cid
    if active:
     done,_=concurrent.futures.wait(active,timeout=5,return_when=concurrent.futures.FIRST_COMPLETED)
     for f in done:f.result();active.pop(f)
    else:time.sleep(3)
    if time.time()-last>15:
     last=time.time();rows=[json.loads(p.read_text()) for p in (ROOT/'raw_results').glob('*.json')]
     log=ROOT/'proxy.log'
     with log.open('rb') as f:f.seek(pos);tail=f.read().decode(errors='replace');pos=f.tell()
     errors=sum(tail.count(s) for s in ['429 Too Many Requests','502 Bad Gateway','503 Service Unavailable','504 Gateway Timeout','APIConnectionError'])
     if errors:last_error=time.time()
     mem=next(int(l.split()[1])/2**20 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
     pressure=mem<cfg['min_memory_gib'] or os.getloadavg()[0]>cfg['max_load']
     if (errors>=3 or pressure) and time.time()-lastscale>60:cfg['workers']=max(1,limit//2);lastscale=time.time();dump(ROOT/'control.json',cfg)
     elif not errors and not pressure and time.time()-last_error>180 and time.time()-lastscale>180 and len(rows)>=(1 if cfg['host']=='cpu' else 8):
      cfg['workers']=min(cfg['target_workers'],limit+16);lastscale=time.time();dump(ROOT/'control.json',cfg)
     dump(ROOT/'status.json',dict(host=cfg['host'],phase='running',assigned=len(ids),processed=len(rows),active=len(active)+legacy_active,legacy_active=legacy_active,queued=len(pending),workers=cfg['workers'],statuses=dict(collections.Counter(x['status'] for x in rows)),recent_api_errors=errors,resource_pressure=pressure,proxy_ok=proxy_ok,time=time.time()))
  dump(ROOT/'status.json',dict(host=cfg['host'],phase='complete',assigned=len(ids),processed=len(ids),active=0,time=time.time()))
if __name__=='__main__':
 try:main()
 except Exception:
  dump(ROOT/'worker_v2_error.json',dict(time=time.time(),traceback=traceback.format_exc()));(ROOT/'pause_generation.request').write_text('Worker error; inspect evidence before resuming');raise
