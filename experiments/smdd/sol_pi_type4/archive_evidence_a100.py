from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'molclaw-type4-a100-20261003'))
import remote
c=remote.connect();s=c.open_sftp();base=Path(__file__).resolve().parent/'a100_evidence';base.mkdir(exist_ok=True)
for name in ['manifest.json','DEPLOYMENT.md','source_validation.json','source_validation.log','preflight/result.json','preflight/config_validation.json','preflight/packages.json','preflight/model_list.json','scheduler_status.json']:
 p=base/name;p.parent.mkdir(parents=True,exist_ok=True);s.get('/yimin/zlc/sol_pi_type4_20261004/'+name,str(p))
s.close();remote.py(c,"""from pathlib import Path
import subprocess,json
r=Path('/yimin/zlc/sol_pi_type4_20261004');mol=Path('/yimin/zlc/molclaw_type4_20261003')
print('BUDGET',json.loads((r/'manifest.json').read_text())['official_agent_config'])
print('SHARED_SLOT_SOURCE',(mol/'gpu_slots.py').read_text()[:10000])
print('SERVICE',subprocess.getoutput('systemctl --user show sol-pi-type4-a100.service molclaw-type4-a100.service -p Id -p ActiveState -p MainPID -p NRestarts'))
""");c.close()
