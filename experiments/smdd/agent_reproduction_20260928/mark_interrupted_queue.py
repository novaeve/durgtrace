from pathlib import Path
import json
from runtime_safety import atomic_json

root=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs/full_type4_flowfix1')
state_path=root/'batch_status.json'
state=json.loads(state_path.read_text())
proc=Path('/proc')/str(state['pid'])/'cmdline'
if proc.exists() and b'run_type4_batch.py' in proc.read_bytes():
    raise RuntimeError('Queue still running; do not change status')
backup=root/'batch_status.before_disk_failure_reconciliation.json'
if not backup.exists():backup.write_bytes(state_path.read_bytes())
state.update(state='interrupted',phase='disk_failure',error='ACE_6: ENOSPC left an empty agent_result.json; batch then failed parsing it. No active queue process. Historical results unchanged.')
atomic_json(state_path,state)
print('Reconciled stopped queue status; no tasks restarted')
