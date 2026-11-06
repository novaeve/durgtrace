from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();s=c.open_sftp();base=Path(__file__).resolve().parent/'a100_evidence/transport_repair';base.mkdir(parents=True,exist_ok=True)
for name in ['repair_current.json','repair_tests/result.json','transport_fix_test.log','repair_fix_test.log','manifest.json','scheduler_status.json']:
 dest=base/name;dest.parent.mkdir(parents=True,exist_ok=True);s.get('/yimin/zlc/sol_pi_type4_20261004/'+name,str(dest))
s.close();c.close();print('FIX_EVIDENCE_SAVED')
