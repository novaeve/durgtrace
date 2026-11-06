from pathlib import Path
import json,time,requests,hashlib
import run
from runtime import ROOT,dump

base=ROOT/'repair_tests';base.mkdir(exist_ok=True)
out=base/'protocol';work=out/'workspace';work.mkdir(parents=True,exist_ok=False)
b=run.Boundary(out,work);server=b.service();url=f'http://127.0.0.1:{server.server_address[1]}'
def tool(rid,name,args):
 return requests.post(url+'/mcp',json={'id':rid,'params':{'name':name,'arguments':args}},timeout=20)
try:
 args={'code':"from pathlib import Path\np=Path('counter.txt');p.write_text(str(int(p.read_text())+1 if p.exists() else 1))\nprint(p.read_text())",'reasoning':'Exactly-once transport test'}
 assert tool('same-id','python',args).status_code==200
 assert tool('same-id','python',args).status_code==200
 assert (work/'counter.txt').read_text()=='1' and b.tools==1
 assert tool('same-id','python',dict(args,code='print(2)')).status_code==500
 (work/'solution.smi').write_text('CCO\n')
 accepted=tool('submit-id','submit',{'file_path':'solution.smi','reasoning':'Transport submission smoke'})
 assert accepted.status_code==200 and accepted.json()['result']['taskComplete']
 before=(out/'accepted_solution.smi').read_bytes();(work/'solution.smi').write_text('CCN\n')
 duplicate=tool('new-submit-id','submit',{'file_path':'solution.smi','reasoning':'Duplicate test'})
 assert duplicate.status_code==200 and (out/'accepted_solution.smi').read_bytes()==before and b.tools==2
 q=requests.post(url+'/v1/chat/completions',json={'messages':[]},timeout=20)
 assert q.status_code==200 and b.api.calls==0 and q.json()['choices'][0]['finish_reason']=='stop'
 assert tool('guard','protocol_guard',{'name':'python','input':{}}).json()['result']['taskComplete']
finally:server.shutdown()
out=base/'budget';work=out/'workspace';work.mkdir(parents=True,exist_ok=False)
saved=dict(calls=93,tokens=2533096,admet_calls=13,boltz_calls=3,tool_calls=44,submitted=False);dump(out/'resume_state.json',saved)
b=run.Boundary(out,work);assert b.api.calls==93 and b.api.total_tokens==2533096 and b.executor.admet_calls==13 and b.executor.boltz_calls==3
b.checkpoint(('predict_boltz',{'smiles':'CCO'}));again=run.Boundary(out,work);assert again.executor.boltz_calls==4 and again.api.calls==93
server=b.service()
try:
 b.api.calls=100;q=requests.post(f'http://127.0.0.1:{server.server_address[1]}/v1/chat/completions',json={'messages':[]},timeout=20)
 assert q.status_code==400 and b.error=='budget_exhausted'
finally:server.shutdown()
print('DUPLICATE_SUBMISSION_AND_CUMULATIVE_BUDGET_TESTS_PASSED',flush=True)
tid=next(t['id'] for t in json.loads((ROOT/'public_tasks.json').read_text()) if not (ROOT/'preflight/solpi'/t['id']).exists())
prompt='This is a runtime transport smoke test, not the molecule benchmark task. Use SMDD python to import rdkit, create probe.txt with 323, and solution.smi with CCO. Use native write and then_run with wc for fused.txt, and update_plan for this test. Then call the SMDD submit tool for solution.smi and finish. Do not call prediction tools.'
result=run.job(tid,True,prompt_override=prompt)
assert result['status']=='complete' and result['submitted'] and result['boltz_calls']==0 and result['admet_calls']==0,result
out=ROOT/'preflight/solpi'/tid;d=json.loads((out/'submission.json').read_text())
assert result['ended']-d['accepted']<6,(result,d)
proof=json.loads((out/'workspace/.pi/loaded-runtime.json').read_text());assert all(proof['config'][k] for k in ['actionFusion','observationPack','evidencePreservingReducer','onlineContextCompact'])
for p in (out/'api').glob('*.json'):
 d=json.loads(p.read_text());assert d['request']['enable_thinking'] is False and d['request']['model']=='deepseek-v4.1-flash'
dump(ROOT/'repair_tests/result.json',{'passed':True,'duplicate_request_exactly_once':True,'accepted_submission_immutable':True,'submission_without_extra_llm':True,'preserved_budgets':True,'native_submission_elapsed':result['ended']-json.loads((out/'submission.json').read_text())['accepted'],'native_smoke_task':tid,'model':'deepseek-v4.1-flash','enable_thinking':False,'all_four_mechanisms':True,'time':time.time()})
print('NATIVE_SUBMISSION_AND_REPAIR_TESTS_PASSED',flush=True)
