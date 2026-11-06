from pathlib import Path
import subprocess, json,pwd
root=Path('/data2/chenfuxin')
print('ROOT_DIRS',[p.name for p in root.iterdir() if p.is_dir() and any(x in p.name.lower() for x in ['codex','claude','opus','type4','boltz'])])
for name in ['smdd_codex_type2_bailian_20260929','smdd_type4_full340_bailian_20260929','smdd_rescore_20261004']:
 p=root/name
 print('DIR',name,[q.name for q in p.iterdir()] if p.exists() else None)
for p in root.glob('smdd_codex*/smoke.py'):print('CODEX_CONFIG_SOURCE',p,p.read_text())
print('GPU',subprocess.getoutput('nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader'))
for row in subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader'],text=True).splitlines():
 pid=row.split(',')[1].strip();p=Path('/proc')/pid
 try:print('GPU_JOB',row,pwd.getpwuid(p.stat().st_uid).pw_name,(p/'cmdline').read_bytes().decode(errors='replace').replace(chr(0),' ')[:380])
 except OSError:pass
print('DISK',subprocess.getoutput('df -h /data2'))
print('SYSTEMD',subprocess.getoutput('systemctl --user list-units --type=service --no-pager --no-legend'))
for p in (root/'smdd_rescore_20261004').glob('jobs/*/*/rescore_status.json'):print('RESCORE',p.parent.name,p.read_text())
print('RESCORE_LOG',(root/'smdd_rescore_20261004/driver.log').read_text()[-1000:])
