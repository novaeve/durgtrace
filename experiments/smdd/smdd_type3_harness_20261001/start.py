from pathlib import Path
import os,sys,subprocess,json,time
ROOT=Path(__file__).resolve().parent
method=sys.argv[1];stage=sys.argv[2]
assert method in ['molclaw','codex'] and stage in ['smoke','full','pilot']
name=method+'_'+stage
pidfile=ROOT/(name+'.pid')
if pidfile.exists():
    p=Path('/proc')/pidfile.read_text().strip()/'stat'
    if p.exists() and p.read_text().split()[2]!='Z':raise RuntimeError('Already running')
cmd=[sys.executable,'-u',str(ROOT/'run.py'),method]+([] if stage=='full' else ['--'+stage])
with (ROOT/(name+'.log')).open('a') as log:
    p=subprocess.Popen(cmd,cwd=ROOT,env=dict(os.environ,SMDD_TYPE3_GPU='0' if method=='molclaw' else '3'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
pidfile.write_text(str(p.pid));time.sleep(2);print(json.dumps({'pid':p.pid,'stage':stage,'method':method,'returncode':p.poll()}))
