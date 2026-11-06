from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();s=c.open_sftp()
base=Path(__file__).resolve().parent
s.put(str(base/'a100/preflight.py'),'/yimin/zlc/sol_pi_type4_20261004/preflight.py')
s.close();c.close();print('PREFLIGHT_UPDATED')
