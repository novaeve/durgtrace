import ast,collections,concurrent.futures,fcntl,hashlib,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ROLE=os.environ.get('EXPERIMENT_ROLE','main')
SUMMARY_FILE='aux_summary.json' if ROLE=='aux' else 'summary.json'
sys.path.insert(0,str(ROOT))
import run as native
from adaptive_gate import STATE
if ROLE=='aux':
 import adaptive_gate
 (ROOT/'aux_rate').mkdir(exist_ok=True);adaptive_gate.ROOT=ROOT/'aux_rate'
M=json.loads((ROOT/'manifest.json').read_text());WORKERS=M['workers']
CASES=json.loads((ROOT/'cases.json').read_text());MODEL='deepseek-v4.1-flash'
CHAT=Path('/data2/chenfuxin/chatdrug_generalization_20260920')
sys.path.insert(0,str(CHAT));import pilot as p
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')
node=next(n for n in ast.parse((CHAT/'full_experiment.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='score')
ns={'p':p};exec(compile(ast.Module(body=[node],type_ignores=[]),'original_score','exec'),ns)
def dump(path,v):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2));tmp.replace(path)
def score(c,candidate):
 if not isinstance(candidate,str) or not candidate.strip():return {'candidate':candidate,'valid':False,'success':False}
 return ns['score'](dict(c,thresholds=[0]*len(c['thresholds'])),candidate)
def finish(c):return ROOT/'evaluated'/c['id']/'result.json'
def transient(row,d):
 if row.get('status')=='interrupted':return True
 if row.get('status')!='error':return False
 aa=sorted((d/'api').glob('*.json'));a=json.loads(aa[-1].read_text()) if aa else {}
 s=str(a.get('error',''))+' '+str(row.get('error',''))
 if 'truncat' in s.lower() or 'data_inspection_failed' in s:return False
 return a.get('http_status') in (408,429,500,502,503,504) or a.get('error_status') in (408,429,500,502,503,504) or any(x in s for x in ('ConnectionError','ConnectTimeout','ReadTimeout','TimeoutError','upstream_stream_error','incomplete_provider_stream','Throttling.'))
if M['method']=='SoL-Pi':
 import relay
 old_complete=relay.Relay.complete
 def guarded(self,body):
  for attempt in range(3):
   try:
    with STATE.acquire():result=old_complete(self,body)
    STATE.success();return result
   except Exception as exc:
    text=str(exc);throttle='429' in text or 'Throttling' in text
    if throttle:STATE.throttle()
    if attempt==2 or not any(x in text for x in ('429','500','502','503','504','ConnectionError','ConnectTimeout','ReadTimeout','upstream_stream_error','incomplete_provider_stream')):raise
    time.sleep(min(60,10*(attempt+1)))
 relay.Relay.complete=guarded
def execute(c):
 path=ROOT/'case_locks'/(c['id']+'.lock');path.parent.mkdir(exist_ok=True)
 with path.open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if finish(c).exists():return json.loads(finish(c).read_text())
  dump(ROOT/'case_owners'/(c['id']+'.json'),dict(pid=os.getpid(),role=ROLE,time=time.time()))
  return execute_unlocked(c)
def execute_unlocked(c):
 if finish(c).exists():return json.loads(finish(c).read_text())
 attempts=[]
 for stage in ('full','infra_retry2','infra_retry3'):
  while shutil_disk_free()<20*2**30:time.sleep(20)
  row=native.execute(c,stage);d=ROOT/'runs'/stage/c['id'];retry=transient(row,d)
  attempts.append(dict(stage=stage,status=row['status'],retryable=retry,native_result=str(d/'result.json')))
  if not retry:break
 r=dict(row,case=c,method=M['method'],provider='Bailian',attempts=attempts,finished=time.time(),reused=False)
 r['score']=score(c,row.get('candidate') if row['status']=='complete' else None);r['evaluation_protocol']='ChatDrug zero thresholds with Kekulize'
 dump(finish(c),r);print(json.dumps({'id':c['id'],'status':r['status'],'success':r['score']['success']}),flush=True);return r
def shutil_disk_free():
 import shutil
 return shutil.disk_usage(ROOT).free
def summary():
 rows=[json.loads(p.read_text()) for p in (ROOT/'evaluated').glob('*/result.json')];statuses=dict(collections.Counter(r['status'] for r in rows));n=sum(bool(r['score']['success']) for r in rows)
 out=dict(method=M['method'],expected=5600,processed=len(rows),reused=sum(r.get('reused',False) for r in rows),success=n,success_rate_full=n/5600,statuses=statuses,workers=WORKERS,rate=STATE.snapshot(),time=time.time())
 dump(ROOT/SUMMARY_FILE,out);return out
def apply_control():
 global WORKERS
 target=json.loads((ROOT/('aux_control.json' if ROLE=='aux' else 'control.json')).read_text())['workers']
 assert isinstance(target,int) and 1<=target<=64
 if target!=WORKERS or STATE.snapshot()['maximum']!=target:
  WORKERS=target;STATE.capacity(target)
def batch(jobs):
 apply_control()
 pending=collections.deque(c for c in jobs if not finish(c).exists())
 with concurrent.futures.ThreadPoolExecutor(64) as pool:
  active=set();last=0
  while pending or active:
   apply_control();gate=STATE.snapshot()
   while pending and not (ROOT/'pause.request').exists() and len(active)<min(WORKERS,gate['limit']) and time.time()>=gate['cooldown_until']:active.add(pool.submit(execute,pending.popleft()))
   if active:
    done,_=concurrent.futures.wait(active,timeout=10,return_when=concurrent.futures.FIRST_COMPLETED)
    for f in done:f.result();active.remove(f)
   else:time.sleep(1)
   if time.time()-last>15:summary();last=time.time()
def validate():
 assert hashlib.sha256((ROOT/'reference_cases.json').read_bytes()).hexdigest()==M['reference_sha256']
 assert len(CASES)==5600 and len({c['id'] for c in CASES})==5600
 for name,h in M['frozen_sources'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
 for c in CASES:assert not score(c,c['smiles'])['success'] and not score(c,None)['success'] and not score(c,'')['success']
 import relay
 cred=relay.load_credentials()
 from urllib.parse import urlsplit
 assert urlsplit(cred['base_url']).hostname=='ws-ucxu0ixh6lwfu9m0.cn-beijing.maas.aliyuncs.com'
def main():
 with (ROOT/'driver.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);validate()
  if '--check' in sys.argv:print('OFFLINE_VALIDATION_OK',flush=True);return
  buckets=collections.defaultdict(list)
  for c in CASES:buckets[(c['task'],c['constraint'])].append(c)
  for v in buckets.values():v.sort(key=lambda c:c['index'])
  ids=json.loads((ROOT/'pilot_ids.json').read_text());byid={c['id']:c for c in CASES};pilot=[byid[i] for i in ids]
  dump(ROOT/'state.json',dict(phase='pilot',time=time.time()));batch(pilot)
  bad=[];receipts=[]
  for c in pilot:
   r=json.loads(finish(c).read_text())
   if r['status'] not in ('complete','provider_limit','timeout'):bad.append(dict(id=c['id'],status=r['status']))
   if r.get('reused'):continue
   d=ROOT/'runs'/r['attempts'][-1]['stage']/c['id'];assert c['instruction'] in (d/'prompt.txt').read_text()
   aa=[json.loads(p.read_text()) for p in sorted((d/'api').glob('*.json'))];ok=[a for a in aa if a.get('response')]
   assert ok,'No provider response '+c['id']
   for a in aa:
    q=a['request'];assert q['model']==MODEL and q['temperature']==0 and q['enable_thinking'] is False
    assert all(k not in q for k in ('max_tokens','max_completion_tokens','reasoning_effort'))
    if a.get('response'):assert a['response']['model']==MODEL
   receipts.append(dict(id=c['id'],responses=len(ok),status=r['status']))
  dump(ROOT/'pilot_acceptance.json',dict(accepted=not bad,task_setting_buckets=28,bad=bad,receipts=receipts))
  complete=[r for r in receipts if r['status']=='complete']
  assert len(complete)>=2,'Pilot lacks complete parsed native episodes'
  native_tools=[]
  for c in pilot:
   r=json.loads(finish(c).read_text())
   if not r.get('reused') and r['status']=='complete':native_tools.append(r.get('tool_calls',0))
  assert any(native_tools),'Pilot lacks native tool execution'
  assert not bad,'Pilot infrastructure failure'
  dump(ROOT/'state.json',dict(phase='full',time=time.time()))
  jobs=[v[i] for i in range(200) for v in buckets.values()];jobs.reverse();batch(jobs);report=summary()
  assert report['processed']==5600
  dump(ROOT/'state.json',dict(phase='complete',summary=report,time=time.time()))
if __name__=='__main__':
 os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
 try:main()
 except Exception as exc:
  dump(ROOT/'state.json',dict(phase='failed',error=str(exc),time=time.time()));(ROOT/'error.log').write_text(traceback.format_exc());raise
