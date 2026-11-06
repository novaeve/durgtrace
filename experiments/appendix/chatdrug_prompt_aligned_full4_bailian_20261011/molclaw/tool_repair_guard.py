"""Resume preserved experiment processes in small batches after real SCP health checks."""
import asyncio,json,os,signal,sys,time,fcntl
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
ROOT=Path(sys.argv[1]);KEY=Path(sys.argv[2]).read_text().strip().split('=',1)[1];LIMIT=int(sys.argv[3])
def dump(name,value):
 p=ROOT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(value,indent=2));t.replace(p)
def processes():
 out={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if p.stat().st_uid!=os.getuid():continue
   st=(p/'stat').read_text().split();out[int(p.name)]={'pid':int(p.name),'start':st[21],'state':st[2],'ppid':int(st[3]),'cwd':str((p/'cwd').resolve()),'ns':str((p/'ns/pid').readlink()),'comm':(p/'comm').read_text().strip()}
  except OSError:pass
 return out
def signal_case(case,sig):
 m=processes();ownns=str(Path('/proc/self/ns/pid').readlink())
 selected={pid for pid,p in m.items() if (p['ns']==case['ns'] and p['ns']!=ownns) or p['cwd']==case['cwd'] or p['cwd'].startswith(case['cwd']+'/')}
 changed=True
 while changed:
  extra={pid for pid,p in m.items() if p['ppid'] in selected}-selected;changed=bool(extra);selected|=extra
 for pid in selected:
  try:os.kill(pid,sig)
  except ProcessLookupError:pass
def factory(headers=None,timeout=None,auth=None):return httpx.AsyncClient(headers=headers,timeout=timeout,auth=auth,trust_env=False)
async def probe():
 t=time.time()
 async with streamablehttp_client('https://scp.intern-ai.org.cn/api/v1/mcp/2/DrugSDA-Tool',headers={'SCP-HUB-API-KEY':KEY},timeout=90,httpx_client_factory=factory) as (rd,wr,_):
  async with ClientSession(rd,wr) as s:
   await s.initialize();v=await s.call_tool('pred_mol_admet',{'smiles_list':['CCO']});d=v.structuredContent or json.loads(v.content[0].text)
   assert not v.isError and d.get('status')=='success' and d.get('json_content'),'No genuine ADMET response'
 return {'time':time.time(),'ok':True,'seconds':round(time.time()-t,2)}
def health():
 try:return asyncio.run(asyncio.wait_for(probe(),120))
 except BaseException as e:return {'time':time.time(),'ok':False,'error':type(e).__name__,'message':str(e).replace(KEY,'[REDACTED]')[:200]}
def alive(c,m):return c['pid'] in m and m[c['pid']]['start']==c['start'] and m[c['pid']]['state']!='Z'
def main():
 lock=(ROOT/'tool_repair_guard.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 record=json.loads((ROOT/'tool_repair_pause.json').read_text());verified=json.loads((ROOT/'scp_repair_verified.json').read_text());assert verified['passed']
 assert time.time()-verified['time']<1800,'Health verification too old'
 cases=[dict(p,id=Path(p['cwd']).name) for p in record['processes'] if p['comm']=='claude']
 # Prioritize existing direct MCP callers, without selecting by chemical outcome.
 def rank(c):
  events=Path(c['cwd'])/'events.jsonl';txt=events.read_text(errors='replace')[-30000:]
  return (0 if 'mcp__molclaw-scp__pred_mol_admet' in txt else 1,c['id'])
 cases.sort(key=rank);pending=cases[:];active=[];completed=[];starts={};paused=False;history=[];lastprobe=0
 h=health();history.append(h);lastprobe=time.time();paused=not h['ok']
 if (ROOT/'tool_repair_guard_error.json').exists():
  (ROOT/'tool_repair_guard_error.json').rename(ROOT/('tool_repair_guard_error_prior_'+str(int(time.time()))+'.json'))
 # Parents may collect existing finals; generation pause files remain in place.
 m=processes()
 for pid in record['controls']:
  old=next(p for p in record['processes'] if p['pid']==pid)
  if alive(old,m):os.kill(pid,signal.SIGCONT)
 dump('tool_repair_guard.pid.json',{'pid':os.getpid(),'time':time.time()})
 while pending or active:
  m=processes()
  for c in active[:]:
   if not alive(c,m):
    active.remove(c);completed.append(c['id'])
  if (ROOT/'tool_repair_guard.stop').exists():
   for c in active:signal_case(c,signal.SIGSTOP)
   paused=True;phase='paused_by_request';break
  if time.time()-lastprobe>90:
   h=health();history.append(h);lastprobe=time.time()
   if not h['ok']:
    for c in active:signal_case(c,signal.SIGSTOP)
    paused=True
   elif paused:
    # Require two consecutive good real tool responses before resuming.
    if len(history)>=2 and history[-2]['ok']:
     for c in active:signal_case(c,signal.SIGCONT)
     paused=False
  if h['ok'] and not paused:
   while pending and len(active)<LIMIT:
    c=pending.pop(0)
    if not alive(c,processes()):completed.append(c['id']);continue
    starts[c['id']]={'time':time.time(),'events_bytes':(Path(c['cwd'])/'events.jsonl').stat().st_size}
    signal_case(c,signal.SIGCONT);active.append(c)
  phase='paused_tool_unhealthy' if paused else 'running_limited'
  dump('tool_repair_guard_status.json',{'time':time.time(),'phase':phase,'limit':LIMIT,'active':[c['id'] for c in active],'pending':[c['id'] for c in pending],'completed':completed,'starts':starts,'health':history[-20:],'protocol_changed':False})
  time.sleep(5)
 else:phase='complete'
 dump('tool_repair_guard_status.json',{'time':time.time(),'phase':phase,'limit':LIMIT,'active':[c['id'] for c in active],'pending':[c['id'] for c in pending],'completed':completed,'starts':starts,'health':history[-20:],'protocol_changed':False})
if __name__=='__main__':
 try:main()
 except BaseException as e:
  # Preserve remaining experiments on controller failure.
  try:
   record=json.loads((ROOT/'tool_repair_pause.json').read_text())
   for c in record['processes']:
    if c['comm']=='claude' and alive(c,processes()):signal_case(c,signal.SIGSTOP)
  finally:dump('tool_repair_guard_error.json',{'time':time.time(),'error':type(e).__name__,'message':str(e).replace(KEY,'[REDACTED]')[:400]})
  raise
