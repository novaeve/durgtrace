"""User-authorized failure policy for unfinished cases; never alter completed answers."""
import collections,fcntl,hashlib,json,os,re,signal,time
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'user_timeout_failures';D.mkdir(exist_ok=True,mode=0o700)
POLICY={'no_progress_seconds':1200,'active_seconds_cap':3600,'denominator':5600,'user_request':'Check normal runtime; skip unreasonably stalled cases and count them as failures','scope':'Remaining episodes only, measured from recovery; pause time excluded','reference':'clean_runtime_summary.json'}
def dump(p,v):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2));t.replace(p)
def proc(pid):
 p=Path('/proc')/str(pid)
 try:
  st=(p/'stat').read_text().split();return {'pid':int(pid),'start':st[21],'state':st[2],'cwd':str((p/'cwd').resolve()),'ns':str((p/'ns/pid').readlink())}
 except OSError:return None
def same(p):
 now=proc(p['pid']);return now and now['start']==p['start'] and now['state']!='Z'
def inspect(c,offset):
 ep=Path(c['cwd'])/'events.jsonl';calls={};meaningful=[];polls=0;terminal=False;tail=[];trailing_poll_wait=0
 with ep.open('rb') as f:f.seek(offset);lines=f.read().decode(errors='replace').splitlines()
 for line in lines:
  try:e=json.loads(line)
  except ValueError:continue
  if e.get('type')=='result':terminal=True
  content=e.get('message',{}).get('content',[])
  if not isinstance(content,list):continue
  for b in content:
   if not isinstance(b,dict):continue
   if b.get('type')=='tool_use':calls[b['id']]=b
   if b.get('type')!='tool_result':continue
   call=calls.get(b.get('tool_use_id'),{});name=call.get('name','unknown');s=json.dumps(b.get('content'),sort_keys=True);cmd=call.get('input',{}).get('command','');err=bool(b.get('is_error')) or bool(re.search(r'Invalid params|ReadTimeout|ConnectTimeout|TaskGroup|operation timed out|no response or progress',s,re.I))
   poll=name=='Bash' and bool(re.search(r'\bsleep\s+\d+',cmd));polls+=poll
   substantive=not err and ((name.startswith('mcp__') and 'success' in s.lower()) or (name in ['Bash','Write','Edit','Read'] and not poll and len(s)>20 and 'completed with no output' not in s))
   sig=hashlib.sha256((name+s).encode()).hexdigest()
   if substantive:meaningful.append(sig);trailing_poll_wait=0
   elif poll and not b.get('is_error'):
    match=re.search(r'\bsleep\s+(\d+)',cmd)
    if match:trailing_poll_wait+=min(600,int(match.group(1)))
   tail.append({'name':name,'error':err,'poll':poll,'output_hash':sig,'length':len(s)})
 return {'signatures':set(meaningful),'poll_results':polls,'terminal':terminal,'tail':tail[-12:],'bytes':ep.stat().st_size,'trailing_poll_wait':trailing_poll_wait}
def terminate(c,reason,st,evidence):
 cid=c['id'];dest=D/(cid+'.json');raw=R/'raw_results'/(cid+'.json');p=proc(c['pid'])
 if raw.exists() or evidence['terminal'] or not same(c):return False
 assert p['cwd']==c['cwd'] and p['ns']==c['ns']
 assert p['ns']!=str(Path('/proc/self/ns/pid').readlink()),'Refuse shared namespace termination'
 members=[]
 for path in Path('/proc').iterdir():
  if not path.name.isdigit():continue
  q=proc(path.name)
  if q and q['ns']==p['ns']:members.append(q)
 if raw.exists():return False
 marker={'id':cid,'time':time.time(),'classification':'user_policy_timeout_failure','reason':reason,'policy':POLICY,'observed_active_seconds':st['active'],'observed_no_progress_seconds':st['idle'],'evidence':evidence['tail'],'native_path':c['cwd'],'processes':members,'count_as_failure':True,'no_retry':True}
 dump(dest,marker)
 # Exact isolated case namespace only; preserve all files and original wrapper output.
 for q in members:
  if same(q):
   try:os.kill(q['pid'],signal.SIGTERM)
   except ProcessLookupError:pass
 time.sleep(2)
 for q in members:
  if same(q):
   try:os.kill(q['pid'],signal.SIGKILL)
   except ProcessLookupError:pass
 return True
def annotate():
 for p in D.glob('source_*.json'):
  raw=R/'raw_results'/p.name
  if not raw.exists():continue
  row=json.loads(raw.read_text())
  if row.get('status')!='error' or 'user_timeout_policy' in row:continue
  m=json.loads(p.read_text());row['user_timeout_policy']={k:m[k] for k in ['classification','reason','observed_active_seconds','observed_no_progress_seconds','count_as_failure','no_retry']};dump(raw,row)
def main():
 lock=(R/'user_timeout_policy.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 dump(R/'user_timeout_policy.json',POLICY);dump(R/'user_timeout_policy.pid.json',{'pid':os.getpid(),'time':time.time()})
 record=json.loads((R/'tool_repair_pause.json').read_text());cases={Path(c['cwd']).name:dict(c,id=Path(c['cwd']).name) for c in record['processes'] if c['comm']=='claude'};states={};last=time.time()
 while True:
  now=time.time();dt=min(30,max(0,now-last));last=now;s=json.loads((R/'tool_repair_guard_status.json').read_text());annotate()
  for cid in s.get('active',[]):
   c=cases[cid];p=proc(c['pid'])
   if not same(c) or p['state'] in ['T','t']:continue
   e=inspect(c,s['starts'][cid]['events_bytes']);good=s.get('phase')=='running_limited' and s.get('health') and s['health'][-1]['ok'] and now-s['health'][-1]['time']<180
   if cid not in states:
    hs=s.get('health',[]);stable=[]
    for h in reversed(hs):
     if not h['ok']:break
     stable.append(h['time'])
    # At bootstrap credit only the contiguous observed healthy window, never unknown paused time.
    initial=min(now-s['starts'][cid]['time'],now-min(stable)) if stable and good else 0
    initial_idle=initial if not e['signatures'] and e['poll_results']>=5 else min(initial,e['trailing_poll_wait'])
    states[cid]={'active':initial,'idle':initial_idle,'seen':e['signatures']}
   else:
    st=states[cid]
    if good:st['active']+=dt;st['idle']+=dt
    if e['signatures']-st['seen']:st['idle']=0;st['seen']|=e['signatures']
   st=states[cid]
   if good and (st['idle']>=1200 or st['active']>=3600):
    terminate(c,'no_effective_progress_20min' if st['idle']>=1200 else 'active_runtime_cap_60min',st,e)
  dump(R/'user_timeout_policy_status.json',{'time':now,'phase':s['phase'],'active':s.get('active',[]),'observations':{k:{'active_seconds':v['active'],'no_progress_seconds':v['idle']} for k,v in states.items()},'failed_ids':[p.stem for p in D.glob('source_*.json')]})
  if s['phase']=='complete':annotate();break
  if (R/'user_timeout_policy.stop').exists():break
  time.sleep(10)
if __name__=='__main__':main()
