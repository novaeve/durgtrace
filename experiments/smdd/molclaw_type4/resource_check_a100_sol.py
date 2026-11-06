from pathlib import Path
import subprocess,json
r=Path('/yimin/zlc/molclaw_type4_20261003')
print('GPU',subprocess.getoutput('nvidia-smi --query-gpu=index,name,memory.free,utilization.gpu --format=csv,noheader'))
print('DISK',subprocess.getoutput('df -h /yimin/zlc'))
print('MOLCLAW_STATUS',(r/'scheduler_status.json').read_text()[:2800] if (r/'scheduler_status.json').exists() else [p.name for p in r.glob('*status*')])
print('MODEL_SECRET_PRESENT',(r/'private/model.env').is_file())
print('NODE_DIRS',[str(p) for p in [r/'node',r/'cli_runtime',r/'rootfs',r/'proxy_env'] if p.exists()])
print('ACCESS_TO_OLD_GPU',subprocess.getoutput('test -f ~/.ssh/id_ed25519 && echo key_present'))
