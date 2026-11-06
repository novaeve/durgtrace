"""Case-local loop control; observe successful native tools and real workspace state."""
from pathlib import Path
import copy,hashlib,json,os,re,threading,time
VERSION='native_codex_loop_guard_v1'
WARNING=("Loop-control notice: The same successful calculation has been repeated with the same actual output and no progress on editing the molecule. Use the existing computed results. Do not execute the same unchanged calculation again. Change strategy and perform a concrete molecular edit, or submit exactly ONE final molecule as <answer>SMILES</answer>. Keep all original task requirements.")
FINAL=("Loop-control notice: An unchanged successful calculation has continued to repeat after the strategy reminder. Stop making tool calls. Use the available results and submit exactly ONE final molecule as <answer>SMILES</answer>, keeping all original task requirements.")
def digest(value):return hashlib.sha256(value).hexdigest()
def text(content):
 if isinstance(content,str):return content
 if isinstance(content,list):return ''.join(b.get('text','') for b in content if b.get('type')=='text')
 return ''
def last_success(body):
 messages=body.get('messages',[])
 if not messages or messages[-1].get('role')!='tool':return None
 tool=messages[-1];output=text(tool.get('content'))
 match=re.search(r'^Process exited with code (-?\d+)\s*$',output,re.M)
 if not match or int(match[1])!=0 or '\nOutput:\n' not in output:return None
 actual=output.split('\nOutput:\n',1)[1]
 call_id=tool.get('tool_call_id')
 for message in reversed(messages[:-1]):
  if message.get('role')=='assistant':
   for call in message.get('tool_calls',[]):
    if call.get('id')==call_id:
     function=call.get('function',{})
     if function.get('name')!='exec_command':return None
     try:args=json.loads(function['arguments'])
     except (KeyError,ValueError):return None
     if not isinstance(args,dict) or not isinstance(args.get('cmd'),str):return None
     return {'call_id':call_id,'command_signature':digest(json.dumps(args,sort_keys=True).encode()),'actual_output_signature':digest(actual.encode())}
 return None
class LoopControl:
 def __init__(self,out,workspace=None):
  self.out=Path(out)
  if workspace is not None:self.workspace=Path(workspace)
  elif self.out.parent.parent.name=='runs':self.workspace=self.out.parents[2]/'work'/self.out.parent.name/self.out.name
  else:self.workspace=self.out/'not_a_formal_workspace'
  self.lock=threading.RLock();self.last_id=None;self.signature=None;self.count=0;self.events=[]
 def fingerprint(self):
  if not self.workspace.is_dir():return None
  state=hashlib.sha256();total=0;files=0
  try:
   for directory,dirs,names in os.walk(self.workspace,followlinks=False):
    relative=Path(directory).relative_to(self.workspace)
    if relative==Path('.'):dirs[:]=[d for d in dirs if d!='.codex']
    for name in list(dirs):
     child=Path(directory)/name
     if child.is_symlink():
      state.update(('symlink_directory:'+str(child.relative_to(self.workspace))+'='+os.readlink(child)).encode());dirs.remove(name)
    dirs.sort();names.sort()
    state.update(('directory:'+str(relative)).encode())
    for name in names:
     p=Path(directory)/name;rel=str(p.relative_to(self.workspace));files+=1
     if files>10000:return None
     if p.is_symlink():
      value='symlink:'+os.readlink(p)
     elif p.is_file():
      st=p.stat();total+=st.st_size
      if st.st_size>16*1024**2 or total>128*1024**2:return None
      identity=(st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
      before=identity;value=digest(p.read_bytes());after=p.stat()
      if before!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):return None
     else:return None
     state.update((rel+'\0'+value+'\0').encode())
   return state.hexdigest()
  except (OSError,ValueError):return None
 def apply(self,body):
  with self.lock:
   q=copy.deepcopy(body);completed=last_success(body);notice=None
   if not completed:
    self.last_id=None;self.signature=None;self.count=0
    return q,notice
   workspace_hash=self.fingerprint()
   if workspace_hash is None:
    self.last_id=None;self.signature=None;self.count=0
    return q,notice
   signature=(completed['command_signature'],completed['actual_output_signature'],workspace_hash)
   if completed['call_id']!=self.last_id:
    self.count=self.count+1 if signature==self.signature else 1
    self.last_id=completed['call_id'];self.signature=signature
   elif signature!=self.signature:
    self.count=1;self.signature=signature
   if self.count>=3:
    final=self.count>=5
    notice={'version':VERSION,'time':time.time(),'consecutive_unchanged_calls':self.count,'action':'request_final_answer' if final else 'change_strategy','tool_choice_override':'none' if final else None,**completed,'workspace_signature':workspace_hash}
    q['messages'].append({'role':'user','content':FINAL if final else WARNING})
    if final:q['tool_choice']='none'
    self.events.append(notice)
    self.out.mkdir(parents=True,exist_ok=True)
    p=self.out/'loop_control_events.json';tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps({'version':VERSION,'events':self.events},indent=2));tmp.replace(p)
   return q,notice
