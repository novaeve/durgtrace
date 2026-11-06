from pathlib import Path
import os,json,subprocess,time,shutil,hashlib
r=Path('/yimin/zlc/sol_pi_type4_20261004');stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime());a=r/'repairs'/('transport_'+stamp);a.mkdir(parents=True)
subprocess.run(['systemctl','--user','stop','sol-pi-type4-a100.service'],check=True)
s=json.loads((r/'scheduler_status.json').read_text());(a/'scheduler_before.json').write_text(json.dumps(s,indent=2))
for n in ['run.py','worker.py','manifest.json','bridge/smdd.ts']:
 p=a/'source_before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(r/n,p)
mol=Path('/yimin/zlc/molclaw_type4_20261003')
d={'archive':str(a),'time':time.time(),'tasks':[it['task'] for it in s['active']['solpi']],'molclaw_pid':subprocess.check_output(['systemctl','--user','show','molclaw-type4-a100.service','-p','MainPID','--value'],text=True).strip(),'molclaw_source_sha256':{n:hashlib.sha256((mol/n).read_bytes()).hexdigest() for n in ['run.py','scheduler.py','gpu_slots.py']}}
(r/'repair_current.json').write_text(json.dumps(d,indent=2));(a/'manifest.json').write_text(json.dumps(d,indent=2));print(json.dumps(d))
for it in s['active']['solpi']:
 out=r/'runs/solpi'/it['task'];p=a/'task_before'/it['task'];p.mkdir(parents=True)
 for n in ['process.json','result.json','record.json','events.jsonl','stderr.log','worker.log','workspace/.pi/session.jsonl']:
  q=out/n
  if q.exists():dest=p/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(q,dest)
ls=(r/'upstream/agent_harness/tools.py').read_text().splitlines()
print('COUNTER_FILENAMES','\n'.join(ls[286:334]));print('TOOL_ERRORS','\n'.join(ls[65:116]))
"""
Only this SoL-Pi scheduler was stopped; its workers and all other services continue.
"""
