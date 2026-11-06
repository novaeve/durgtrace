from pathlib import Path
import sys,os,json,subprocess,time
ROOT=Path(__file__).resolve().parent
stage=sys.argv[1];assert stage in ['pilot','full']
if stage=='full':assert json.loads((ROOT/'pilot_validation.json').read_text())['passed']
pidfile=ROOT/(stage+'.pid')
if pidfile.exists():
    p=Path('/proc')/pidfile.read_text().strip()/'stat'
    if p.exists() and p.read_text().split()[2]!='Z':raise RuntimeError('Already running')
with (ROOT/(stage+'.log')).open('a') as log:
    proc=subprocess.Popen([sys.executable,'-u',str(ROOT/'run.py'),stage],cwd=ROOT,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
pidfile.write_text(str(proc.pid));time.sleep(2)
print(json.dumps({'stage':stage,'pid':proc.pid,'returncode':proc.poll()}))
