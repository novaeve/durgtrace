"""Reuse the existing official evaluator without exposing it to either harness."""
import os,sys,time,json,fcntl,traceback
from pathlib import Path
from run import ROOT,BASE,configure_gpu
from runtime import dump
import runtime,evaluate
configure_gpu()
evaluate.ROOT=ROOT;evaluate.gpu_run=runtime.gpu_run
for name in ['tasks','upstream','eval_bridge.py']:
    p=ROOT/name
    if not p.exists():p.symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
with (ROOT/'score.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    while True:
        for method in ['molclaw','codex']:
            for p in sorted((ROOT/'runs'/method).glob('*/result.json')):
                generation=json.loads(p.read_text())
                if generation['status']=='error':continue
                dest=ROOT/'evaluation'/method/p.parent.name/'result.json'
                if dest.exists():continue
                try:
                    r=evaluate.evaluate(p.parent.name,method)
                    if r['status']=='errored' and any(s.get('name')=='Validity' and s.get('status')=='failed' for s in r.get('steps',[])):
                        dump(dest.with_name('raw_result.json'),r)
                        r['status']='failed';r['adjudication']={'reason':'Invalid molecule counts as failed, per user instruction','raw_result':'raw_result.json'};dump(dest,r)
                    print(json.dumps({'method':method,'task':p.parent.name,'status':r['status']}),flush=True)
                except Exception:
                    dump(dest.parent/'infrastructure_error.json',{'time':time.time(),'traceback':traceback.format_exc()})
        summary={}
        for method in ['molclaw','codex']:
            rows=[json.loads(p.read_text()) for p in (ROOT/'evaluation'/method).glob('*/result.json')]
            summary[method]={'expected':52,'evaluated':len(rows),**{k:sum(r['status']==k for r in rows) for k in ['passed','failed','errored']}}
        dump(ROOT/'evaluation/summary.json',summary)
        if all(r['evaluated']==52 for r in summary.values()):break
        time.sleep(20)
