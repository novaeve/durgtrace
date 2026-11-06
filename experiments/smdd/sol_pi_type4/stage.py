from pathlib import Path
import sys,json,shlex
LOCAL=Path(__file__).resolve().parent
sys.path[:0]=[str(LOCAL.parent/'gpu-scheduling-20261001'),str(LOCAL.parent/'molclaw-type4-a100-20261003')]
import manage
ROOT='/data2/chenfuxin/sol_pi_type4_20261004';A100='/yimin/zlc/sol_pi_type4_20261004'
gpu=manage.connect('gpu');g=gpu.open_sftp()
def command(c,code):
 _,o,e=c.exec_command('python3 -c '+shlex.quote(code),timeout=60);data=o.read();err=e.read();assert o.channel.recv_exit_status()==0,err.decode();return data
command(gpu,"""from pathlib import Path
import shutil,subprocess
r=Path('/data2/chenfuxin/sol_pi_type4_20261004');r.mkdir(exist_ok=True)
for name in ['private','bridge','runs','preflight','source']: (r/name).mkdir(exist_ok=True)
(r/'private').chmod(0o700)
base=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004')
for name in ['public_inputs','tasks','upstream']:
 p=r/name
 if not p.exists():p.symlink_to(base/name,target_is_directory=True)
shutil.copy2(base/'public_tasks.json',r/'public_tasks.json')
for name in ['runtime.py','gpu_slots.py','evaluate.py','smdd_eval_bridge.py']:shutil.copy2(base/name,r/'source'/name)
print('public task sets prepared')
""")
for name in ['runtime.py','gpu_slots.py','evaluate.py','smdd_eval_bridge.py']:g.get(ROOT+'/source/'+name,str(LOCAL/('source_'+name)))
print('STAGED 340 public-only tasks for 5090-only launch; no credential transfer or SSH authorization changes')
g.close();gpu.close()
