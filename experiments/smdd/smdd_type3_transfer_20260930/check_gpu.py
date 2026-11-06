from pathlib import Path
import json,subprocess
r=Path('/data2/chenfuxin/smdd_type3_transfer_20260930')
for name in ['chatdrug.state.json','agentdrug.state.json','deepseek.state.json']:
 print(name,(r/name).read_text())
for p in list(r.glob('runs/deepseek/*/workspace/boltz_results/*/boltz.log'))+list(r.glob('evaluation/*/*/queue/*/boltz.log')):
 print(str(p.relative_to(r)),p.read_text(errors='replace')[-1500:])
for p in r.glob('evaluation/*/*/container.log'):print(str(p.relative_to(r)),p.read_text(errors='replace')[-1000:])
print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
