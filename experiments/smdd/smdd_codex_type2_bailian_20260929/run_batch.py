import concurrent.futures,csv,datetime,fcntl,hashlib,json,math,os,shutil,signal,subprocess,threading,time
from pathlib import Path
from smoke import BASE,provider_env,command

MODEL='deepseek-v4.1-flash'
RUN=BASE/'run';WORK=BASE/'work'
LOCK=threading.Lock()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def public_prompt(description):
 return f'''You are the SMDD-Bench Type 2 Interaction Point Discovery agent. Work only in the current workspace.

Public task:
{description}

The workspace contains receptor.pdb. Do not search for, access, or infer hidden evaluator files, ground truth, prior answers, or any other task directories. Analyze the receptor structure and produce solution.csv in the current workspace. It must contain exactly 3 rows, no header, with columns x,y,z,type as required by the task. Use the provided pocket center and radius. You may run structural analysis with Python; the command '{BASE}/bin/python' provides RDKit, BioPython, NumPy, and SciPy. Before finishing, validate that solution.csv exists and has the exact required format. Do not merely describe the answer: create the file. Do not inspect environment variables or credentials.
'''
def task(t):
 tid=t['task_id'];out=RUN/tid;work=WORK/tid;out.mkdir(exist_ok=True);work.mkdir(exist_ok=True)
 done=out/'agent_result.json'
 if done.exists():return json.loads(done.read_text())
 cfg,env=provider_env();shutil.copy2(BASE/'public_inputs'/tid/'receptor.pdb',work/'receptor.pdb')
 prompt=public_prompt(t['description']);(out/'prompt.txt').write_text(prompt)
 start=time.monotonic();started=now();rc=None
 print(json.dumps({'event':'task_start','task_id':tid,'at':started}),flush=True)
 with (out/'codex_events.jsonl').open('w') as so,(out/'codex_stderr.log').open('w') as se:
  p=subprocess.Popen(command(cfg['base_url'],out,prompt),cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
  dump(out/'process.json',{'pid':p.pid,'started_at':started})
  try:rc=p.wait(timeout=3600)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=20)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   rc=124
 usage={};thread=None;types={};tool_calls=0
 for line in (out/'codex_events.jsonl').read_text(errors='replace').splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  typ=x.get('type');types[typ]=types.get(typ,0)+1
  if typ=='thread.started':thread=x.get('thread_id')
  if typ=='turn.completed':usage=x.get('usage',{})
  if typ=='item.completed' and x.get('item',{}).get('type') in ['command_execution','tool_call','mcp_tool_call']:tool_calls+=1
 solution=work/'solution.csv';fmt=False;reason='missing solution.csv'
 if solution.is_file():
  shutil.copy2(solution,out/'solution.csv')
  try:
   rows=list(csv.reader(solution.read_text().splitlines()));assert len(rows)==3 and all(len(r)==4 for r in rows)
   assert all(math.isfinite(float(v)) for row in rows for v in row[:3]);assert all(row[3].strip() for row in rows)
   fmt=True;reason=None
  except Exception:reason='solution.csv must be 3 rows of finite x,y,z,type without header'
 meta={'task_id':tid,'harness':'codex-cli-native','model':MODEL,'provider':'Alibaba Bailian','status':'submitted' if fmt and rc==0 else 'error','exit_code':rc,'format_valid':fmt,'format_error':reason,'runtime_seconds':round(time.monotonic()-start,3),'thread_id':thread,'usage':usage,'tool_calls':tool_calls,'event_counts':types,'started_at':started,'completed_at':now(),'receptor_sha256':hashlib.sha256((work/'receptor.pdb').read_bytes()).hexdigest(),'solution_sha256':hashlib.sha256(solution.read_bytes()).hexdigest() if solution.is_file() else None,'reviewer_enabled':False,'memory_enabled':False}
 dump(done,meta);print(json.dumps({'event':'task_end','task_id':tid,'status':meta['status'],'seconds':meta['runtime_seconds']}),flush=True);return meta
def progress(tasks,state):
 with LOCK:
  rows=[json.loads((RUN/t['task_id']/'agent_result.json').read_text()) for t in tasks if (RUN/t['task_id']/'agent_result.json').exists()]
  dump(BASE/'progress.json',{'state':state,'total':len(tasks),'completed':len(rows),'submitted':sum(r['status']=='submitted' for r in rows),'errors':sum(r['status']!='submitted' for r in rows),'updated_at':now(),'tasks':rows})
if __name__=='__main__':
 BASE.mkdir(exist_ok=True);RUN.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True)
 lock=(BASE/'batch.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 tasks=json.loads((BASE/'public_tasks.json').read_text());assert len(tasks)==25 and len({t['task_id'] for t in tasks})==25
 assert json.loads((BASE/'smoke/result.json').read_text())['passed']
 cfg,_=provider_env()
 dump(BASE/'manifest.json',{'name':'codex_bailian_deepseek_type2_20260929','harness':'Codex CLI 0.149.0','model':MODEL,'provider':'Alibaba Bailian','base_url':cfg['base_url'],'key_source':'/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env','key_moved':False,'task_count':25,'task_ids':[t['task_id'] for t in tasks],'workers':2,'max_task_wall_seconds':3600,'reviewer_enabled':False,'memory_enabled':False,'hidden_data_present':False,'baseline_reference':'H1-normal_codex_type2_20260901','environment_change':'Native molecular Python environment replaces previous CPU Docker Python wrapper; model provider replaced with Bailian DeepSeek; same Codex CLI version and public task set.','started_at':now()})
 progress(tasks,'running_pilot');r=task(tasks[0]);progress(tasks,'pilot_complete')
 if r['status']!='submitted':progress(tasks,'failed_pilot');raise SystemExit(2)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(task,t) for t in tasks[1:]]
  for f in concurrent.futures.as_completed(futures):f.result();progress(tasks,'running')
 progress(tasks,'agent_complete');print('AGENT_BATCH_COMPLETE',flush=True)
