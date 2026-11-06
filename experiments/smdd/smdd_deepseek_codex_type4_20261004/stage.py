import sys,os,json,shlex,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu-scheduling-20261001'))
import manage
LOCAL=Path(__file__).resolve().parent
ROOT='/data2/chenfuxin/smdd_deepseek_codex_type4_20261004'
c=manage.connect('gpu');s=c.open_sftp()
def command(code):
 _,o,e=c.exec_command('python3 -c '+shlex.quote(code),timeout=60);data=o.read();err=e.read();assert o.channel.recv_exit_status()==0,err.decode();return data
command("from pathlib import Path\nr=Path("+repr(ROOT)+");r.mkdir(exist_ok=True)\nfor name in ['upstream/agent_harness','public_inputs','tasks','source','bin','runs','preflight']: (r/name).mkdir(parents=True,exist_ok=True)")
source='/data2/chenfuxin/smdd_type3_transfer_20260930/upstream/agent_harness'
for name in s.listdir(source):
 if name.endswith('.py'):
  data=s.open(source+'/'+name,'rb').read()
  (LOCAL/name).write_bytes(data)
  with s.open(ROOT+'/upstream/agent_harness/'+name,'wb') as f:f.write(data)
for name,source in [('type3_run.py','/data2/chenfuxin/smdd_type3_harness_20261001/run.py'),('original_runtime.py','/data2/chenfuxin/smdd_type3_transfer_20260930/runtime.py')]:s.get(source,str(LOCAL/name))
manifest=json.loads(command("from pathlib import Path\nimport yaml,json,shutil\nr=Path("+repr(ROOT)+")\ntasks=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/benchmark/tasks')\nrows=[]\nfor src in sorted(tasks.glob('smdd_004_*')):\n tid=src.name;d=yaml.safe_load((src/'task.yaml').read_text());out=r/'public_inputs'/tid;out.mkdir(exist_ok=True)\n for name in ['complex.pdb','reference.sdf']:shutil.copy2(src/name,out/name)\n public={'id':tid,'description':d['description']};(r/'tasks'/f'{tid}.json').write_text(json.dumps(public));rows.append(public)\nassert len(rows)==340\n(r/'public_tasks.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))"))
(LOCAL/'public_tasks.json').write_text(json.dumps(manifest,indent=2))
command("from pathlib import Path\nimport shutil\nr=Path("+repr(ROOT)+")\nshutil.copy2('/data2/chenfuxin/smdd_codex_type2_bailian_20260929/bin/codex',r/'bin/codex')\nprint('staged340')")
print('STAGED 340 public-only tasks and upstream SMDD harness; existing Codex binary copied; no key transfer')
s.close();c.close()
