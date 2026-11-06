import os,json,time,fcntl,traceback
os.environ['EXPERIMENT_ROLE']='aux'
import driver as d
from pathlib import Path
ROOT=d.ROOT
def preflight():
 d.validate();ids=json.loads((ROOT/'pilot_ids.json').read_text());byid={c['id']:c for c in d.CASES};evidence=[];complete=0;tools=0
 for i in ids:
  c=byid[i];out=ROOT/'runs/full'/i
  assert c['instruction'] in (out/'prompt.txt').read_text(),i
  aa=[json.loads(p.read_text()) for p in sorted((out/'api').glob('*.json'))]
  assert aa and any(x.get('response') for x in aa),i
  for a in aa:
   q=a['request'];assert q['model']==d.MODEL and q['temperature']==0 and q['enable_thinking'] is False
   assert all(k not in q for k in ('max_tokens','max_completion_tokens','reasoning_effort'))
   if a.get('response'):assert a['response']['model']==d.MODEL
  assert any(c['instruction'] in str(x.get('content','')) for x in aa[0]['request']['messages'] if x['role']=='user'),i
  p=d.finish(c);r=json.loads(p.read_text()) if p.exists() else {}
  complete+=r.get('status')=='complete';tools+=r.get('tool_calls',0)
  evidence.append(dict(id=i,final_status=r.get('status','inflight'),responses=sum(bool(a.get('response')) for a in aa)))
 assert complete>=2 and tools>0
 d.dump(ROOT/'aux_preflight.json',dict(accepted=True,pilot_complete_count=complete,pilot_total=28,pilot_all_complete=all(e['final_status']!='inflight' for e in evidence),real_payloads_verified=True,evidence=evidence,excluded_ids=ids,case_locking=True,time=time.time()))
 return set(ids)
def main():
 with (ROOT/'aux_driver.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);excluded=preflight()
  jobs=sorted((c for c in d.CASES if c['id'] not in excluded),key=lambda c:(c['index'],c['task'],c['constraint']))
  assert len(jobs)==5572
  d.dump(ROOT/'aux_state.json',dict(phase='full_nonpilot',excluded_pilot=28,expected_jobs=len(jobs),time=time.time()))
  d.batch(jobs);d.dump(ROOT/'aux_state.json',dict(phase='complete',time=time.time()))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  d.dump(ROOT/'aux_state.json',dict(phase='failed',error=str(exc),time=time.time()));(ROOT/'aux_error.log').write_text(traceback.format_exc())
  if isinstance(exc,(AssertionError,ValueError,KeyError,TypeError)):(ROOT/'pause.request').write_text('Auxiliary validation failed; inspect aux_error.log')
  raise
