import json,subprocess
import run
work=run.ROOT/'preflight';work.mkdir(exist_ok=True);(work/'.home').mkdir(exist_ok=True);(work/'.codex').mkdir(exist_ok=True)
code='import os,rdkit; assert not os.path.exists("'+str(run.LANG)+'/data/answers.json"); assert not os.path.exists("'+str(run.OLD)+'/run"); assert not os.path.exists("/data2/chenfuxin/molingo_20260922/private"); print("isolation_rdkit_ok")'
subprocess.run(run.sandbox(work)+['python','-c',code],check=True)
cmd=run.command(work)
with (work/'events.jsonl').open('w') as out,(work/'stderr.log').open('w') as err:
    proc=subprocess.run(cmd,input='Use your shell tool to run Python, import rdkit, compute 17*19, and write it to probe.txt. Read it back using a shell tool. Finish saying SMOKE_OK. Work only in /workspace.',text=True,stdout=out,stderr=err,timeout=240)
events=[json.loads(s) for s in (work/'events.jsonl').read_text().splitlines() if s.strip()]
tools=sum(e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution' for e in events)
assert proc.returncode==0 and (work/'probe.txt').read_text().strip()=='323' and tools>=1
run.dump(work/'result.json',{'passed':True,'shell_tool_calls':tools,'model':run.MODEL})
print('LIVE_CODEX_TOOL_SMOKE_PASSED')
