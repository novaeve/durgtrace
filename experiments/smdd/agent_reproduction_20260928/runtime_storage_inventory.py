from pathlib import Path
import json
import re
import shutil
root=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs')
stats={}
for p in root.rglob('samples_*.pt'):
    if 'generation' not in p.parts:continue
    category='per_step_snapshots' if re.fullmatch(r'samples_\d+\.pt',p.name) else 'initial_or_final_snapshots'
    stat=stats.setdefault(category,{'count':0,'bytes':0})
    stat['count']+=1;stat['bytes']+=p.stat().st_size
print(json.dumps({'snapshot_usage':stats,'disk_free_gib':shutil.disk_usage(root).free/1024**3},indent=2))
