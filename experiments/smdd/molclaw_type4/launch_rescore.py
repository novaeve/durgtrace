import sys,shlex
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
c=manage.connect('gpu');s=c.open_sftp();root='/data2/chenfuxin/smdd_rescore_20261004'
s.put(str(Path(__file__).with_name('rescore_driver.py')),root+'/driver.py')
cmd='nohup /data2/chenfuxin/agent_reproduction_20260928/envs/boltz_smdd/bin/python -u '+root+'/driver.py > '+root+'/driver.log 2>&1 < /dev/null & echo $!'
_,o,e=c.exec_command(cmd);print('RESCORE_PID',o.read().decode().strip());print(e.read().decode());s.close();c.close()
