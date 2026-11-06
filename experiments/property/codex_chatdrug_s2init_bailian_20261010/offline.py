"""Verify native sandbox, exact cases, model boundary and directional scoring without generation."""
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import driver,run as native,loop_control
from common import score,dump
driver.validate()
toy='CCOC(=O)c1ccc(O)cc1'
for prop,low,high in [('LogP','CCO','c1ccccc1'),('QED','CCO',toy)]:
 for direction,source,candidate,sign in [('higher',low,high,1),('lower',high,low,-1)]:
  case={'id':'synthetic','smiles':source,'property':prop,'direction':direction,'objectives':[[prop,sign]],'thresholds':[1000]}
  assert score(case,candidate)['success'],(prop,direction)
  assert not score(case,source)['success']
  assert not score(case,None)['success']
assert native.parse('<answer>CCO</answer>')=='CCO'
assert native.parse('<answer>CCO</answer><answer>CCC</answer>') is None
assert not driver.transient({'status':'timeout'},ROOT/'nonexistent')
assert not driver.transient({'status':'provider_limit'},ROOT/'nonexistent')
assert driver.transient({'status':'error','error':'ReadTimeout'},ROOT/'nonexistent')
with tempfile.TemporaryDirectory(dir=ROOT) as folder:
 w=Path(folder);(w/'.home').mkdir();(w/'.codex').mkdir()
 hidden=str(ROOT/'manifest.json');credential='/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env'
 script="import pathlib,json;from rdkit import Chem,rdBase;from rdkit.Chem import Crippen,QED;m=Chem.MolFromSmiles('CCO');assert m;assert not pathlib.Path("+repr(hidden)+").exists();assert not pathlib.Path("+repr(credential)+").exists();print(json.dumps({'rdkit':rdBase.rdkitVersion,'logp':Crippen.MolLogP(m),'qed':QED.qed(m),'hidden_files_absent':True}))"
 cmd=native.sandbox(w)+['/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python','-c',script]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);assert p.returncode==0,p.stderr
 sandbox=json.loads(p.stdout)
 version=subprocess.run(native.sandbox(w)+['/runner/codex','--version'],capture_output=True,text=True,timeout=30)
 assert version.returncode==0 and '0.149.0' in version.stdout,version.stderr
with tempfile.TemporaryDirectory(dir=ROOT) as folder:
 w=Path(folder)/'work';w.mkdir();guard=loop_control.LoopControl(Path(folder)/'out',w)
 for n in range(1,6):
  call={'id':'test_'+str(n),'type':'function','function':{'name':'exec_command','arguments':json.dumps({'cmd':'python -c \"print(1)\"'})}}
  b={'messages':[{'role':'user','content':'unchanged task'},{'role':'assistant','tool_calls':[call]},{'role':'tool','tool_call_id':call['id'],'content':'Process exited with code 0\nOutput:\n1\n'}],'tool_choice':'auto'}
  q,notice=guard.apply(b)
  if n<3:assert notice is None
  if n==3:assert notice['action']=='change_strategy'
  if n==5:assert notice['action']=='request_final_answer' and q['tool_choice']=='none'
pilot,_=driver.ordered()
report={'passed':True,'cases':1600,'pilot_cases':len(pilot),'native_cli':version.stdout.strip(),'sandbox':sandbox,'directional_controls_passed':True,'amplitude_ignored_control_passed':True,'single_submission_parser_verified':True,'loop_guard_verified':True,'provider':'Bailian','model':driver.MODEL,'provider_host':driver.MANIFEST['provider_host']}
dump(ROOT/'offline_validation.json',report)
print(json.dumps(report),flush=True)
