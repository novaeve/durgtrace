import argparse,fcntl,hashlib,json,os,pathlib,subprocess,sys,time,traceback
BASE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'harness'))
TASKS=pathlib.Path('/home/chenfuxin/smdd-migration/SMDD-Bench/tasks')
def dump(p,data):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(p)
def one(method,tid,index,gpu):
 import run_smoke as s
 from transport_adapter import complete
 root=BASE/method;s.ROOT=root
 os.environ['CHATDRUG_GPU']=str(gpu)
 s.agent_loop.call_llm_completions=complete
 original=s.run.start_container
 def isolated(*a,**kw):
  kw['task_id']='full340-'+method+'-'+tid
  return original(*a,**kw)
 s.run.start_container=isolated
 if method=='agentdrug':
  from agentdrug_smdd import run_agent
  s.run.run_agent=run_agent
 config=s.AgentConfig();config.model='bailian/deepseek-v4.1-flash'
 if method=='agentdrug':config.temperature=0
 s.run.ensure_network();proxy=s.run.start_proxy()
 out=root/'run'/tid;ap=out/'agent_result.json';ep=root/'evaluator'/tid/'result.json'
 agent=json.loads(ap.read_text()) if ap.exists() else s.run.run_single_task(tid,index,str(TASKS),config,str(root/'run'),proxy,gpu)
 if ep.exists():evaluation=json.loads(ep.read_text())
 else:
  evaluation=None
  for attempt in range(2):
   evaluation=s.evaluate(tid,out)
   if evaluation.get('status')!='errored':break
   dump(root/'evaluator'/tid/f'infrastructure_attempt_{attempt+1}.json',evaluation)
 assert agent['admet_calls']<=15 and agent['boltz_calls']<=8
 tool_errors=[]
 for name in ['chatdrug_events.jsonl','agentdrug_events.jsonl']:
  if (out/name).exists():
   tool_errors.extend(x for x in (json.loads(line) for line in (out/name).read_text().splitlines()) if x.get('event')=='boltz_error')
 row={'task':tid,'agent':agent['status'],'evaluation':evaluation['status'],'admet_calls':agent['admet_calls'],'boltz_calls':agent['boltz_calls'],'turns':agent['turns_used'],'budget_exhausted':agent['admet_calls']>=15 or agent['boltz_calls']>=8,'agent_error':agent.get('error'),'tool_infrastructure_errors':len(tool_errors)}
 dump(root/'records'/f'{tid}.json',row)
 return row
def summary(root,ids):
 rows=[json.loads((root/'records'/f'{t}.json').read_text()) for t in ids if (root/'records'/f'{t}.json').exists()]
 passed=sum(r.get('evaluation')=='passed' for r in rows)
 data={'total':len(ids),'completed':len(rows),'passed':passed,'failed':sum(r.get('evaluation')=='failed' for r in rows),'infrastructure_errors':sum(r.get('evaluation')=='errored' or r.get('agent')=='error' or r.get('tool_infrastructure_errors',0)>0 for r in rows),'budget_exhausted':sum(r.get('budget_exhausted',False) for r in rows),'accuracy_denominator':len(ids),'accuracy':passed/len(ids),'state':'complete' if len(rows)==len(ids) else 'running','results':rows}
 dump(root/'summary.json',data);return data
def main():
 p=argparse.ArgumentParser();p.add_argument('method',choices=['chatdrug','agentdrug']);p.add_argument('--gpu',type=int,required=True);p.add_argument('--task');p.add_argument('--index',type=int,default=0);a=p.parse_args()
 root=BASE/a.method;root.mkdir(exist_ok=True)
 if a.task:
  try:print(json.dumps(one(a.method,a.task,a.index,a.gpu)),flush=True)
  except Exception:traceback.print_exc();raise
  return
 lock=(root/'batch.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 ids=(BASE/'tasks340.txt').read_text().splitlines();assert len(ids)==340 and len(set(ids))==340
 summary(root,ids)
 for i,tid in enumerate(ids):
  if (root/'records'/f'{tid}.json').exists():continue
  dump(root/'current.json',{'task':tid,'index':i,'gpu':a.gpu,'started':time.time()})
  logs=root/'logs';logs.mkdir(exist_ok=True)
  print('START',tid,flush=True)
  with (logs/(tid+'.log')).open('a') as log:
   try:r=subprocess.run([sys.executable,str(BASE/'batch.py'),a.method,'--gpu',str(a.gpu),'--task',tid,'--index',str(i)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=43200)
   except subprocess.TimeoutExpired:r=None
  if not (root/'records'/f'{tid}.json').exists():
   dump(root/'records'/f'{tid}.json',{'task':tid,'agent':'error','evaluation':'errored','infrastructure_error':'task_timeout_12h' if r is None else 'worker_exit_'+str(r.returncode)})
  report=summary(root,ids);print('FINISHED',tid,'completed',report['completed'],'passed',report['passed'],'errors',report['infrastructure_errors'],flush=True)
 report=summary(root,ids)
 (root/'experiment.exit').write_text('0' if not report['infrastructure_errors'] else '2')
 (root/'RESULTS.md').write_text(f"{a.method}: {report['completed']}/340 terminal tasks; {report['passed']}/340 passed; {report['failed']} failed; {report['infrastructure_errors']} infrastructure errors.\n")
if __name__=='__main__':main()
