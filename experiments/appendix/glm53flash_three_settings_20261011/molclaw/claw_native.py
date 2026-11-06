import pathlib,json,re,sys,subprocess,concurrent.futures,fcntl,collections,hashlib
ROOT=pathlib.Path(__file__).resolve().parent
from common import score
sys.path.insert(0,'/data2/chenfuxin/chatdrug_generalization_20260920')
import full_experiment as benchmark
def dump(path,obj):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2));tmp.replace(path)
def summarize(stage):
 rows=[json.loads(f.read_text()) for f in (ROOT/'runs'/stage).glob('*/result.json')];groups={}
 for row in rows:
  key='ChatDrug' if row['case']['benchmark']=='ChatDrug' else row['case']['property'];g=groups.setdefault(key,collections.Counter())
  g[row['status']]+=1;g['success']+=bool(row.get('score',{}).get('success'))
 out={'processed':len(rows),'groups':groups,'errors':[{'id':r['id'],'error':r.get('error')} for r in rows if r['status']=='error']}
 dump(ROOT/'runs'/stage/'summary.json',out);return out
def run_case(case,stage):
 out=ROOT/'native/MolClaw'/stage/case['id'];out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return
 row={'id':case['id'],'case':case}
 proc=subprocess.run([sys.executable,str(ROOT/'claw_agent.py'),stage,case['id']],capture_output=True,text=True)
 if proc.returncode:
  row.update(status='error',error='AGENT_RUNTIME_EXIT_'+str(proc.returncode))
 else:
  events=[]
  for line in (out/'events.jsonl').read_text().splitlines():
   try:events.append(json.loads(line))
   except ValueError:continue
  final=next((e for e in reversed(events) if e.get('type')=='result'),{})
  text=final.get('result','');candidate=None;failure=None
  if not text and (out/'result.md').exists():text=(out/'result.md').read_text()
  tags=re.findall(r'<answer>\s*(.*?)\s*</answer>',text,re.S|re.I)
  if len(tags)==1:
   candidate=tags[0].strip()
   if not candidate or any(c.isspace() for c in candidate):candidate=None
  if candidate is None:failure='NO_UNAMBIGUOUS_SINGLE_SMILES'
  row.update(status='complete',candidate=candidate,score=score(case,candidate),model_failure=failure,usage=final.get('usage',{}),num_turns=final.get('num_turns'),runtime_subtype=final.get('subtype'),runtime_is_error=final.get('is_error'),tool_calls=collections.Counter(block.get('name') for e in events if e.get('type')=='assistant' for block in e.get('message',{}).get('content',[]) if block.get('type')=='tool_use'))
  if final.get('is_error'):row.update(status='error',error='AGENT_'+str(final.get('subtype')))
 dump(out/'result.json',row);print(json.dumps({'id':case['id'],'status':row['status'],'success':row.get('score',{}).get('success'),'error':row.get('error')}),flush=True)
def main():
 stage=sys.argv[1];assert stage in ['smoke','pilot','full']
 out=ROOT/'runs'/stage;out.mkdir(parents=True,exist_ok=True)
 lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=json.loads((benchmark.PREP/'cases.json').read_text())
 if stage=='smoke':cases=cases[:1]
 elif stage=='pilot':
  buckets={}
  for c in cases:buckets.setdefault((c['benchmark'],c['task'] if c['benchmark']=='ChatDrug' else c['property'],c['constraint'],c['direction']),c)
  cases=list(buckets.values());assert len(cases)==34
 else:
  gate=json.loads((ROOT/'runs/pilot/summary.json').read_text());assert gate['processed']==34 and not gate['errors']
 cfg={'model':'deepseek-v4.1-flash','provider':'Alibaba Bailian via LiteLLM','upstream_commit':'180abb7679ffc5b1ca9974e7390e141d8098f642','mode':'both','expected':len(cases),'workers':2,'submission':'exactly one final SMILES; no trajectory oracle','code_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['benchmark_runner.py','smoke_agent.py','launch_proxy.py']}}
 dump(out/'run_config.json',cfg)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  jobs=[pool.submit(run_case,c,stage) for c in cases]
  for job in concurrent.futures.as_completed(jobs):job.result();summarize(stage)
 result=summarize(stage)
 if result['errors']:raise SystemExit(2)
if __name__=='__main__':main()
