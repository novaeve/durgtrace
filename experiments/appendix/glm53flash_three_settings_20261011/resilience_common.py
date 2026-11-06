"""Operations-only recovery; never resample valid scientific outcomes."""
import hashlib,json,os,subprocess,time
from pathlib import Path

def read(path,default=None):
 try:return json.loads(Path(path).read_text())
 except (FileNotFoundError,ValueError):return default

def write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
 tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)

def alive(script,arg=None):
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:args=(proc/'cmdline').read_bytes().split(b'\0')
  except OSError:continue
  if str(script).encode() in args and (arg is None or arg.encode() in args):return True
 return False

def start(root,cmd,name):
 proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=(root/(name+'.watchdog.log')).open('a'),stderr=subprocess.STDOUT,start_new_session=True)
 with (root/'resilience_events.jsonl').open('a') as f:f.write(json.dumps({'event':'started','service':name,'pid':proc.pid,'time':time.time()})+'\n')
 return proc.pid

def recoverable(row):
 # Invalid SMILES, property failure, native wall/idle timeout, token limit and refusals are terminal.
 if row.get('status')=='interrupted':return True
 if row.get('status')!='error':return False
 if row.get('infrastructure_parallel_claim'):return True
 if row.get('retryable'):return True
 text=str(row.get('error','')).lower()
 return any(x in text for x in ('experiment_halted','provider_hold','connection refused','connection reset','incomplete_provider_stream','transport_error','gateway_timeout'))

def move_within(root,source,destination):
 if not source.exists():return
 assert source.resolve().is_relative_to(root.resolve()) and destination.resolve().is_relative_to(root.resolve())
 destination.parent.mkdir(parents=True,exist_ok=True);source.rename(destination)

def repair_idle_codex(root):
 method=root/'codex';archive=root/'auto_recovery'/('Codex_'+str(time.time_ns()))
 jobs=read(method/'jobs.json',[]);repaired=[];kept={}
 for job in jobs:
  setting=job['setting'];ident=job['case']['id'];final=method/'runs/Codex'/setting/ident
  native=method/'native/runs'/setting/ident;work=method/'native/work'/setting/ident
  row=read(final/'result.json')
  claim=(row or {}).get('infrastructure_parallel_claim')
  if claim:
   cached=None
   for key in ('scratch_final','native_result'):
    path=Path(claim.get(key,'/nonexistent'))
    if not path.resolve().is_relative_to(root.resolve()):continue
    candidate=read(path)
    if candidate and candidate.get('status') in ('complete','timeout','provider_limit'):
     cached=dict(candidate);break
   if cached is not None:
    if 'case' in cached:assert cached['case']==job['case']
    else:
     import importlib.util
     source=method/'common.py'
     assert hashlib.sha256(source.read_bytes()).hexdigest()==read(method/'manifest.json')['common_sha256']
     spec=importlib.util.spec_from_file_location('parallel_cached_score',source)
     module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
     cached.update(case=job['case'],score=module.score(job['case'],cached.get('candidate') if cached['status']=='complete' else None),model='glm-5.3-flash',retryable=False)
    cached.update(setting=setting,method='Codex',native_result=claim.get('native_result'),parallel_cache_restored=True)
    cached.pop('infrastructure_parallel_claim',None)
    target=archive/setting/ident;target.mkdir(parents=True,exist_ok=True)
    (target/'previous_claimed_result.json').write_bytes((final/'result.json').read_bytes())
    write(final/'result.json',cached)
    repaired.append({'setting':setting,'id':ident,'cached_result_promoted':True});continue
  if row is not None and not recoverable(row):
   kept[str(final/'result.json')]=hashlib.sha256((final/'result.json').read_bytes()).hexdigest();continue
  nrow=read(native/'result.json')
  if row is None and nrow and not recoverable(nrow) and nrow.get('status') in ('complete','timeout','provider_limit'):
   # Let the original native wrapper recover its already finished outcome without new API calls.
   continue
  if not any(p.exists() for p in (final,native,work)):continue
  target=archive/setting/ident
  for label,path in [('final',final),('native',native),('work',work)]:move_within(root,path,target/label)
  repaired.append({'setting':setting,'id':ident,'archive':str(target)})
 for path,digest in kept.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
 if repaired:write(archive/'audit.json',{'repaired_unfinished':repaired,'preserved_final_hashes':kept,'time':time.time()})
 return repaired

def repair_idle_direct(root):
 method=root/'direct/uncapped_retry1120';archive=root/'auto_recovery'/('Direct_'+str(time.time_ns()))
 jobs=read(method/'jobs.json',[]);repaired=[]
 for job in jobs:
  path=method/'runs/GLM_direct'/job['setting']/job['case']['id']
  if read(path/'result.json') is not None:continue
  if (path/'result.json').exists():
   move_within(root,path/'result.json',archive/job['setting']/job['case']['id']/'unreadable_result.json')
  if (path/'api.json').exists():
   receipt=read(path/'api.json')
   if receipt and receipt.get('response',{}).get('model')=='glm-5.3-flash':continue
   move_within(root,path/'api.json',archive/job['setting']/job['case']['id']/'unreadable_api.json')
  # Network outcomes with no observed valid completion can be retried, with the lost attempt archived.
  for file in list(path.glob('*error*.json')):
   destination=archive/job['setting']/job['case']['id']/file.name
   move_within(root,file,destination);repaired.append(str(destination))
 return repaired

def permanent_driver_error(state):
 text=str(state.get('error','')).lower()
 return any(x in text for x in ('assertionerror','source pin','offline validation','pilot native','duplicate','unexpected model configuration'))
