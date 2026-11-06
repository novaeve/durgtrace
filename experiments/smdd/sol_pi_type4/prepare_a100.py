import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();root='/yimin/zlc/sol_pi_type4_20261004'
remote.py(c,"from pathlib import Path\nr=Path("+repr(root)+");r.mkdir(exist_ok=True)\n(r/'jobs').mkdir(exist_ok=True)")
s=c.open_sftp();s.put(str(Path(__file__).with_name('a100_worker.py')),root+'/gpu_worker.py');s.chmod(root+'/gpu_worker.py',0o700)
_,o,e=c.exec_command('/usr/bin/python3 '+root+'/gpu_worker.py');o.channel.sendall(json.dumps({'action':'probe'}).encode());o.channel.shutdown_write()
print('PREPARED_COMPUTE_WORKER',root,'RESOURCE_PROBE',o.read().decode().strip());print(e.read().decode());s.close();c.close()
