from pathlib import Path
import json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(ROOT/'verify.py')],check=True)
for method in ['molclaw','codex']:
    subprocess.run([sys.executable,str(ROOT/'start.py'),method,'full'],check=True)
pidfile=ROOT/'score.pid'
if pidfile.exists():
    stat=Path('/proc')/pidfile.read_text().strip()/'stat'
    if stat.exists() and stat.read_text().split()[2]!='Z':raise RuntimeError('Scorer already running')
with (ROOT/'score.log').open('a') as log:
    proc=subprocess.Popen([sys.executable,'-u',str(ROOT/'score.py')],cwd=ROOT,env=dict(os.environ,SMDD_TYPE3_GPU='7'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
pidfile.write_text(str(proc.pid));time.sleep(2);assert proc.poll() is None
print(json.dumps({'scorer_pid':proc.pid,'inference_gpus':[0,3],'evaluation_gpu':7}))
