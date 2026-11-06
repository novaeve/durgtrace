from pathlib import Path
import os,sys,json,time,subprocess,argparse,fcntl,traceback
from runtime import ROOT,ROOTFS,UPSTREAM,gpu_run,dump

def evaluate(tid,method):
 out=ROOT/'runs'/method/tid;ev=ROOT/'evaluation'/method/tid;ev.mkdir(parents=True,exist_ok=True)
 if (ev/'result.json').exists():return json.loads((ev/'result.json').read_text())
 if not (out/'solution.smi').exists() or not (out/'solution.smi').read_text().strip():
  result={'task_id':tid,'status':'failed','reason':'missing_or_empty_submission','steps':[]};dump(ev/'result.json',result);return result
 queue=ev/'queue';queue.mkdir(exist_ok=True)
 args=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind',str(ROOTFS),'/',
 '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/root','--tmpfs','/eval','--tmpfs','/work',
 '--ro-bind',str(ROOT/'tasks'/tid),'/eval/task','--ro-bind',str(out),'/eval/output',
 '--bind',str(ev),'/eval/results','--ro-bind',str(UPSTREAM),'/eval/code','--bind',str(queue),'/queue',
 '--ro-bind',str(ROOT/'eval_bridge.py'),'/bridge.py','--chdir','/eval','--clearenv',
 '--setenv','PATH','/opt/conda/bin:/usr/bin:/bin','--setenv','LD_LIBRARY_PATH','/opt/conda/lib','--setenv','HOME','/tmp',
 '--setenv','OMP_NUM_THREADS','1','--setenv','OPENBLAS_NUM_THREADS','1','--setenv','MKL_NUM_THREADS','1','--setenv','CUDA_VISIBLE_DEVICES','',
 '/opt/conda/bin/python','/bridge.py']
 with (ev/'container.log').open('w') as log:
  p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
  try:
   while p.poll() is None:
    for req in queue.glob('*/request.json'):
     done=req.parent/'done.json'
     if done.exists():continue
     d=json.loads(req.read_text())
     try:
      rc=gpu_run(req.parent/d['yaml_name'],req.parent/'out',req.parent/'boltz.log',d['samples'])
      cifs=list((req.parent/'out').rglob('*.cif'))
      if rc and not cifs:raise RuntimeError('Boltz failed without structures; inspect boltz.log')
      result={'returncode':rc,'structures':len(cifs)}
     except Exception as e:result={'error':type(e).__name__+': '+str(e)}
     dump(done,result)
    time.sleep(1)
  finally:
   if p.poll() is None:p.terminate();p.wait(timeout=20)
 if not (ev/'result.json').exists():raise RuntimeError('Evaluator failed; see '+str(ev/'container.log'))
 return json.loads((ev/'result.json').read_text())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--once',action='store_true');ap.add_argument('--method',choices=['deepseek','chatdrug','agentdrug']);a=ap.parse_args()
 ev=ROOT/'evaluation';ev.mkdir(exist_ok=True)
 lock=(ev/'worker.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 methods=[a.method] if a.method else ['chatdrug','agentdrug','deepseek']
 while True:
  for method in methods:
   for r in sorted((ROOT/'runs'/method).glob('*/result.json')):
    if (ev/method/r.parent.name/'result.json').exists():continue
    result=evaluate(r.parent.name,method);print(json.dumps({'method':method,'task':r.parent.name,'status':result['status']}),flush=True)
    if result['status']=='errored':print(json.dumps({'pending_retry':r.parent.name,'method':method,'reason':'evaluation_error_preserved'}),flush=True)
  summary={}
  for method in methods:
   rows=[json.loads(p.read_text()) for p in (ev/method).glob('*/result.json')]
   summary[method]={'expected':52,'evaluated':len(rows),'passed':sum(r['status']=='passed' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'errored':sum(r['status']=='errored' for r in rows)}
  dump(ev/'summary.json',summary)
  if a.once or all(s['evaluated']==52 for s in summary.values()):break
  time.sleep(20)
if __name__=='__main__':main()
