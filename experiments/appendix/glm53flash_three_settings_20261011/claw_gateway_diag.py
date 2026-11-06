import json,os,signal,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'gateway_claw.py';text=p.read_text().replace("{'error':'unknown_route'}","{'error':{'message':'unsupported route '+self.path,'code':'unknown_route'}}")
p.write_text(text)
pid=256924
cmd=Path('/proc')/str(pid)/'cmdline'
if cmd.exists() and str(p).encode() in cmd.read_bytes():os.kill(pid,signal.SIGTERM)
py=ROOT/'runtime/chatdrug_generalization_20260920/venv/bin/python'
p=subprocess.Popen([str(py),'-u',str(p)],stdin=subprocess.DEVNULL,stdout=(ROOT/'gateway_claw.log').open('a'),stderr=subprocess.STDOUT,start_new_session=True)
print('GATEWAY_DIAGNOSTICS_PID',p.pid)
