from pathlib import Path
import json,sys,subprocess,traceback,time,shutil
from runtime import ROOT,dump
method,tid=sys.argv[1:3];out=ROOT/'runs'/method/tid;out.mkdir(parents=True,exist_ok=True)
try:
 with (out/'worker.log').open('a') as log:
  cmd=[sys.executable,str(ROOT/'run.py'),tid]
  if '--resume' in sys.argv:cmd.append('--resume')
  p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
  agent=json.loads((out/'result.json').read_text()) if (out/'result.json').exists() else {'status':'worker_error','exit':p.returncode}
  scoring='not_evaluated'
  if (out/'solution.smi').exists():
   p=subprocess.run([sys.executable,str(ROOT/'evaluate.py'),tid,str(out)],stdout=log,stderr=subprocess.STDOUT)
   result=out/'evaluation/result.json'
   if result.exists():scoring=json.loads(result.read_text())['status']
   else:scoring='evaluation_missing'
  dump(out/'record.json',{'method':method,'task':tid,'agent':agent['status'],'evaluation':scoring,'completed':time.time()})
except Exception as exc:
 (out/'worker_error.log').write_text(traceback.format_exc())
 dump(out/'record.json',{'method':method,'task':tid,'agent':'worker_error','evaluation':'not_evaluated','error':str(exc),'completed':time.time()})
