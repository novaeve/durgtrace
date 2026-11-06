from pathlib import Path
import sys,shlex
LOCAL=Path(__file__).resolve().parent
sys.path.insert(0,str(LOCAL.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();s=c.open_sftp();root='/yimin/zlc/sol_pi_type4_20261004'
s.put(str(LOCAL/'install_npm_a100.py'),root+'/install_npm.py')
_,o,e=c.exec_command('nohup /yimin/zlc/molclaw_type4_20261003/rootfs/opt/conda/bin/python -u '+root+'/install_npm.py > '+root+'/install.log 2>&1 < /dev/null & echo $!');print('INSTALL_VALIDATION_PID',o.read().decode().strip());print(e.read().decode());s.close();c.close()
