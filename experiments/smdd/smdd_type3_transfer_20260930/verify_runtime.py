from pathlib import Path
import json,sys,shutil
from runtime import ROOT,UPSTREAM,isolated,Executor,API,dump
from agent_harness.config import AgentConfig
from agent_harness.obfuscate import obfuscate_task
import yaml
ids=sorted(p.name for p in (ROOT/'tasks').glob('smdd_003_*'))
assert len(ids)==52
for tid in ids:
 p=ROOT/'tasks'/tid
 assert len(list((p/'gt_results/boltz_results_gt_dock/predictions/gt_dock').glob('*.cif')))==10,tid
(ROOT/'task_list.txt').write_text('\n'.join(ids)+'\n')
work=ROOT/'smoke/work';work.mkdir(parents=True,exist_ok=True)
script="""import os,json
import rdkit,numpy,pandas,scipy,sklearn,Bio,biotite,openbabel,plip
assert not os.path.exists('/data2/chenfuxin')
assert not os.path.exists('/eval/code')
assert not os.path.exists('/root/.ssh')
from pathlib import Path
Path('test.smi').write_text('CCO')
print(json.dumps({'imports':'ok','host_files_hidden':True}))
"""
text,rc=isolated(['python','-c',script],work);print(text);assert rc==0
ex=Executor(str(work),AgentConfig())
assert 'accepted' in ex.run_submit({'file_path':'test.smi'})[0]
api=API(ROOT/'smoke/high_tools')
messages=[{'role':'user','content':'Call echo with text ok. After the tool responds, answer ok.'}]
tools=[{'type':'function','function':{'name':'echo','description':'Echo text','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}}]
a=api.complete(messages,tools=tools,cap=4096);m=a['choices'][0]['message'];assert m.get('tool_calls')
messages.append(m)
for tc in m['tool_calls']:messages.append({'role':'tool','tool_call_id':tc['id'],'content':'ok'})
b=api.complete(messages,tools=tools,cap=4096);assert b['choices'][0]['message'].get('content')
dump(ROOT/'smoke/preflight.json',{'tasks':52,'isolation':'passed','python_imports':'passed','high_tool_roundtrip':'passed','ground_truth_structures':520})
print('Preflight passed')
