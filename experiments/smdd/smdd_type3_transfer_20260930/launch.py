from pathlib import Path
import os,sys,json,time,subprocess,argparse
from runtime import ROOT,dump
PY='/data2/chenfuxin/pmo_1k_20260924/venv/bin/python'

def supervise(method):
 for stage,args in [('pilot',['--pilot']),('full',[])]:
  dump(ROOT/(method+'.state.json'),{'stage':stage,'status':'running','pid':os.getpid(),'time':time.time()})
  p=subprocess.run([PY,str(ROOT/'run_experiment.py'),method]+args,cwd=ROOT)
  if p.returncode:
   dump(ROOT/(method+'.state.json'),{'stage':stage,'status':'error','exit_code':p.returncode,'time':time.time()});return p.returncode
 dump(ROOT/(method+'.state.json'),{'stage':'full','status':'complete','expected':52,'time':time.time()});return 0

def launch():
 assert json.loads((ROOT/'smoke/preflight.json').read_text())['high_tool_roundtrip']=='passed'
 manifest={'benchmark':'SMDD-type3','tasks':52,'model':'deepseek-v4.1-flash','enable_thinking':True,'reasoning_effort':'high','started':time.time(),'processes':{}}
 for method in ['deepseek','chatdrug','agentdrug','evaluation']:
  pidpath=ROOT/(method+'.pid')
  if pidpath.exists():
   try:os.kill(int(pidpath.read_text()),0);raise RuntimeError('Already running '+method)
   except ProcessLookupError:pass
  env=dict(os.environ,PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',SMDD_TYPE3_GPU='0' if method=='evaluation' else '4')
  cmd=[PY,str(ROOT/'evaluate.py')] if method=='evaluation' else [PY,str(ROOT/'launch.py'),'--supervise',method]
  with (ROOT/(method+'.log')).open('a') as log:
   p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  pidpath.write_text(str(p.pid));manifest['processes'][method]=p.pid
 dump(ROOT/'run_manifest.json',manifest)
 req=ROOT/'experiment_request.json'
 if req.exists():
  d=json.loads(req.read_text());d.update(status='running',data_source='official open source, no historical Claude outputs used');d.pop('blocker',None);dump(req,d)
 print(json.dumps(manifest))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--supervise');a=ap.parse_args()
 if a.supervise:raise SystemExit(supervise(a.supervise))
 launch()
