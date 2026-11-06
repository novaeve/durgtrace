from pathlib import Path
import sys,shlex,hashlib
LOCAL=Path(__file__).resolve().parent
sys.path[:0]=[str(LOCAL.parent/'gpu-scheduling-20261001'),str(LOCAL.parent/'molclaw-type4-a100-20261003')]
import manage,remote
gpu=manage.connect('gpu');c=remote.connect();g=gpu.open_sftp();s=c.open_sftp();dest='/yimin/zlc/sol_pi_type4_20261004'
src='/data2/chenfuxin/sol_pi_type4_20261004/sol-pi-runtime.tar.gz';tmp=LOCAL/'sol-pi-runtime.tar.gz'
g.get(src,str(tmp));s.put(str(tmp),dest+'/sol-pi-runtime.tar.gz')
digest=hashlib.sha256(tmp.read_bytes()).hexdigest()
remote.py(c,"""from pathlib import Path
import subprocess,json,hashlib
r=Path('/yimin/zlc/sol_pi_type4_20261004');assert hashlib.sha256((r/'sol-pi-runtime.tar.gz').read_bytes()).hexdigest()==DIGEST
subprocess.run(['tar','-xzf',str(r/'sol-pi-runtime.tar.gz'),'-C',str(r)],check=True)
mol=Path('/yimin/zlc/molclaw_type4_20261003')
for name in ['upstream','node','public_inputs','tasks']:
 p=r/name
 if not p.exists():p.symlink_to(mol/name,target_is_directory=True)
print('EXTRACTED_PUBLIC_RUNTIME',subprocess.getoutput('du -sh '+str(r/'SoL-Pi')))
print('NPM',subprocess.getoutput('command -v npm'))
""".replace('DIGEST',repr(digest)))
print('RUNTIME_SHA256_MATCH',digest,'no credentials transferred')
g.close();s.close();gpu.close();c.close()
