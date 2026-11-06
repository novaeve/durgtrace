from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();s=c.open_sftp();base=Path(__file__).resolve().parent/'a100_evidence'
for name in ['manifest.json','scheduler_status.json']:
 s.get('/yimin/zlc/sol_pi_type4_20261004/'+name,str(base/name))
s.get('/yimin/zlc/sol_pi_type4_20261004/runs/solpi/smdd_004_A2A_Adenosine_0/workspace/boltz_results/call_1/boltz_provenance.json',str(base/'first_gpu_prediction.json'))
s.close();c.close();print('CURRENT_STATUS_AND_GPU_EVIDENCE_SAVED')
