import sys
import remote
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
c=manage.connect('gpu');s=c.open_sftp()
r='/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_parallel3/source/'
for n in ['evaluate_type4.py','smdd_eval_bridge.py','smdd_backends.py','runtime_safety.py']:
 s.get(r+n,str(remote.ROOT/('liddia_'+n)))
print('Downloaded evaluator transport source')
s.close()
manage.execute(c,"""from pathlib import Path
p=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_waitresume3/smdd_004_ACE_6/evaluation/queue/6597ac23ae944fb1bdf58102d6722938/gpu/boltz_828669eadd56/boltz.log')
print(p.read_text(errors='replace')[-4000:] if p.exists() else 'log missing')
""")
c.close()
