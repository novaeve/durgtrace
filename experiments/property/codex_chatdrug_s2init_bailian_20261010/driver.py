"""Fresh Codex+Bailian generation with a single final S2-scored submission per case."""
import collections,concurrent.futures,fcntl,hashlib,json,os,sys,time,traceback
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import run as native,relay,legacy_relay
from common import score,dump
from adaptive_gate import STATE
MODEL='deepseek-v4.1-flash';WORKERS=16
CASES=json.loads((ROOT/'cases.json').read_text())
MANIFEST=json.loads((ROOT/'manifest.json').read_text())
STAGES=('full','infra_retry2','infra_retry3')
_original_load=legacy_relay.load_credentials
def bailian_credentials():
 values=_original_load();url=urlsplit(values['base_url'])
 assert url.scheme=='https' and url.hostname==MANIFEST['provider_host'] and url.path==MANIFEST['provider_base_path'] and not url.username and not url.query,'Frozen Bailian endpoint required'
 return values
relay.load_credentials=bailian_credentials
legacy_relay.load_credentials=bailian_credentials
def final(c):return ROOT/'evaluated'/c['id']/'result.json'
def out(c,stage):return ROOT/'runs'/stage/c['id']
def records(c,stage):return [json.loads(p.read_text()) for p in sorted((out(c,stage)/'api').glob('*.json'))]
def transient(row,directory):
 if row.get('status')=='interrupted':return True
 if row.get('status')!='error':return False
 paths=sorted((directory/'api').glob('*.json'))
 if paths:
  a=json.loads(paths[-1].read_text());text=str(a.get('error',''))+' '+str(a.get('upstream_error',''))
  if 'truncat' in text.lower() or 'data_inspection_failed' in text.lower():return False
  if a.get('error') and (a.get('error_status') in (408,429,500,502,503,504) or a.get('http_status') in (408,429,500,502,503,504) or 'Throttling.' in text or 'upstream_stream_error' in text):return True
 return row.get('error') in ('ConnectionError','ConnectTimeout','ReadTimeout','TimeoutError') or (row.get('error')=='RuntimeError' and not paths and not (directory/'events.jsonl').exists())
def execute(c):
 if final(c).exists():return json.loads(final(c).read_text())
 attempts=[]
 for stage in STAGES:
  row=native.execute(c,stage)
  retry=transient(row,out(c,stage))
  attempts.append({'stage':stage,'status':row['status'],'retryable':retry,'native_result':str(out(c,stage)/'result.json')})
  if not retry:break
 a=records(c,stage)
 response_models=sorted({x['response']['model'] for x in a if x.get('response') and x['response'].get('model')})
 assert all(m==MODEL for m in response_models)
 result=dict(row,case=c,setting='2_s2_prompt_chatdrug',method='Codex',provider='Bailian',attempts=attempts,
  stage=stage,harness_variant=MANIFEST['harness_variant'],provider_response_models=response_models,retryable=retry,finished=time.time())
 result['score']=score(c,row.get('candidate') if row['status']=='complete' else None)
 result['evaluation_calls']=1
 dump(final(c),result)
 print(json.dumps({'id':c['id'],'property':c['property'],'status':row['status'],'success':result['score']['success'],'attempts':len(attempts)}),flush=True)
 return result
def summary():
 rows=[json.loads(p.read_text()) for p in (ROOT/'evaluated').glob('*/result.json')]
 groups=[]
 for prop in ('LogP','QED'):
  rr=[r for r in rows if r['case']['property']==prop]
  success=sum(bool(r['score']['success']) for r in rr)
  groups.append({'property':prop,'expected':800,'processed':len(rr),'success':success,'success_rate_processed':success/len(rr) if rr else None,'statuses':dict(collections.Counter(r['status'] for r in rr))})
 report={'method':'Codex','model':MODEL,'provider':'Bailian','setting':'2_s2_prompt_chatdrug','expected':1600,'processed':len(rows),'workers':WORKERS,'groups':groups,'rate_control':STATE.snapshot(),'time':time.time()}
 dump(ROOT/'summary.json',report);return report
def ordered():
 buckets=collections.defaultdict(list)
 for c in CASES:buckets[(c['task'],c['constraint'])].append(c)
 assert len(buckets)==8
 for items in buckets.values():items.sort(key=lambda c:c['index'])
 jobs=[items[i] for i in range(max(map(len,buckets.values()))) for items in buckets.values() if i<len(items)]
 assert len(jobs)==1600
 return jobs[:8],jobs[8:]
def validate():
 assert native.MODEL==MODEL and relay.MODEL==MODEL
 for name,h in MANIFEST['frozen_harness'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
 for name,key in [('jobs.json','jobs_sha256'),('cases.json','cases_sha256'),('common.py','common_sha256')]:assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==MANIFEST[key]
 assert hashlib.sha256(Path(MANIFEST['native_codex_binary']).read_bytes()).hexdigest()==MANIFEST['native_codex_binary_sha256']
 bailian_credentials()
 assert len(CASES)==1600 and collections.Counter(c['property'] for c in CASES)=={'LogP':800,'QED':800}
 for c in CASES:
  assert c['instruction']==f"Optimize the molecule {c['smiles']} to have a {c['direction']} {c['property']} value."
  assert not score(c,c['smiles'])['success'] and not score(c,None)['success']
def batch(selected):
 pending_jobs=collections.deque(c for c in selected if not final(c).exists())
 with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
  active=set();last=time.monotonic()
  while pending_jobs or active:
   gate=STATE.snapshot()
   while pending_jobs and len(active)<min(WORKERS,gate['limit']) and time.time()>=gate['cooldown_until']:
    active.add(pool.submit(execute,pending_jobs.popleft()))
   if active:
    done,_=concurrent.futures.wait(active,timeout=10,return_when=concurrent.futures.FIRST_COMPLETED)
    for f in done:f.result();active.remove(f)
   else:time.sleep(1)
   if time.monotonic()-last>=15:summary();last=time.monotonic()
 return summary()
def pilot_check(pilot):
 evidence=[];bad=[]
 for c in pilot:
  r=json.loads(final(c).read_text());stage=r['stage'];aa=records(c,stage)
  if r['status'] not in ('complete','timeout','provider_limit'):bad.append({'id':c['id'],'status':r['status'],'error':r.get('error')})
  assert c['instruction'] in (out(c,stage)/'prompt.txt').read_text()
  real=[a for a in aa if a.get('response')]
  assert real,'Actual Bailian model receipt missing'
  for a in aa:
   q=a['request'];assert q['model']==MODEL and q['temperature']==0 and q['enable_thinking'] is False
   assert all(k not in q for k in ('max_tokens','max_completion_tokens','reasoning_effort','thinking'))
   if a.get('response'):assert a['response']['model']==MODEL
  first=aa[0]['request']
  assert any(c['instruction'] in str(m.get('content','')) for m in first.get('messages',[]) if m.get('role')=='user')
  evidence.append({'id':c['id'],'property':c['property'],'status':r['status'],'provider_responses':len(real),'tool_calls':r.get('tool_calls',0),'model':MODEL})
 assert any(e['tool_calls'] for e in evidence),'Native Codex tool operation not observed'
 dump(ROOT/'pilot_acceptance.json',{'accepted':not bad,'episodes':8,'evidence':evidence,'errors':bad,'time':time.time()})
 assert not bad,'Pilot infrastructure failure'
def main():
 with (ROOT/'driver.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  validate();pilot,full=ordered()
  if '--check' in sys.argv:print('DATASET_PROVIDER_AND_SCORER_CHECK_PASSED',flush=True);return
  STATE.capacity(WORKERS)
  dump(ROOT/'state.json',{'phase':'pilot','workers':WORKERS,'model':MODEL,'provider':'Bailian','time':time.time()})
  batch(pilot);pilot_check(pilot)
  dump(ROOT/'state.json',{'phase':'full','workers':WORKERS,'model':MODEL,'provider':'Bailian','time':time.time()})
  batch(full);report=summary();assert report['processed']==1600
  errors=sum(g['statuses'].get('error',0)+g['statuses'].get('interrupted',0) for g in report['groups'])
  dump(ROOT/'state.json',{'phase':'attention_required' if errors else 'complete','workers':WORKERS,'model':MODEL,'provider':'Bailian','processed':1600,'error_count':errors,'time':time.time()})
if __name__=='__main__':
 os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
 try:main()
 except Exception as exc:
  dump(ROOT/'state.json',{'phase':'failed','error':str(exc),'model':MODEL,'time':time.time()})
  (ROOT/'driver_error.log').write_text(traceback.format_exc());raise
