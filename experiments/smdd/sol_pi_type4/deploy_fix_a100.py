from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();base=Path(__file__).resolve().parent
remote.py(c,"""from pathlib import Path
import json,shutil,subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004');d=json.loads((r/'repair_current.json').read_text())
assert subprocess.run(['systemctl','--user','is-active','sol-pi-type4-a100.service'],capture_output=True,text=True).stdout.strip()!='active'
assert not (r/'run_legacy.py').exists();shutil.copy2(Path(d['archive'])/'source_before/run.py',r/'run_legacy.py')
""")
s=c.open_sftp()
for src,dst in [('a100/run_fixed.py','run.py'),('a100/worker.py','worker.py'),('bridge/smdd.ts','bridge/smdd.ts'),('bridge/transport.mjs','bridge/transport.mjs'),('test_transport.mjs','test_transport.mjs'),('test_repair.py','test_repair.py')]:s.put(str(base/src),'/yimin/zlc/sol_pi_type4_20261004/'+dst)
s.close()
remote.py(c,"""from pathlib import Path
import subprocess,os,py_compile
r=Path('/yimin/zlc/sol_pi_type4_20261004');py='/yimin/zlc/molclaw_type4_20261003/rootfs/opt/conda/bin/python'
for n in ['run.py','worker.py','run_legacy.py','test_repair.py']:py_compile.compile(str(r/n),doraise=True)
env=dict(os.environ,OPENSSL_CONF='/dev/null',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
for proxy in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','all_proxy','ALL_PROXY']:env.pop(proxy,None)
for label,args in [('transport',[str(r/'node/bin/node'),str(r/'test_transport.mjs')]),('repair',[py,'-u',str(r/'test_repair.py')])]:
 with (r/(label+'_fix_test.log')).open('w') as log:
  p=subprocess.Popen(args,cwd=r,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
 print('START_TEST',label,p.pid)
""");c.close()
