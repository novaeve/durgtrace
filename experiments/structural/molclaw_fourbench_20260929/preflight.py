import subprocess,tempfile,json
from pathlib import Path
from run import ROOT,sandbox,cases,parse,S2,LANG
assert len(cases())==3800
assert len([c for c in cases() if c['index']==0])==10
assert parse('x <answer>CCO</answer>')=='CCO'
assert parse('<answer>CC</answer><answer>CCC</answer>') is None
assert parse('<summary>pending</summary>') is None
assert parse('<answer><smiles>CCO</smiles></answer>')=='CCO'
work=ROOT/'preflight';work.mkdir(exist_ok=True)
code='import os,rdkit; assert not os.path.exists("'+str(LANG)+'/data/answers.json"); assert not os.path.exists("'+str(S2)+'/runs"); assert not os.path.exists("/data2/chenfuxin/molclaw_20260924/private"); print("runtime_and_gold_isolation_ok")'
subprocess.run(sandbox(work)+['python','-c',code],check=True)
print('case_counts_and_native_parser_ok')
