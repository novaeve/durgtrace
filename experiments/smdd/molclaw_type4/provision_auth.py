"""User explicitly authorized this credential destination on 2026-10-03."""
import sys
import remote
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
old=manage.connect('gpu');src=old.open_sftp()
with src.open('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env','rb') as f:data=f.read()
src.close();old.close()
c=remote.connect();s=c.open_sftp();directory='/yimin/zlc/molclaw_type4_20261003/private'
try:s.mkdir(directory,mode=0o700)
except IOError:s.stat(directory)
s.chmod(directory,0o700)
target=directory+'/model.env'
with s.open(target,'wb') as f:
 s.chmod(target,0o600);f.write(data)
del data
assert s.stat(target).st_mode&0o777==0o600
s.close();c.close();print('Model authentication provisioned; directory 0700, file 0600; no secret printed')
