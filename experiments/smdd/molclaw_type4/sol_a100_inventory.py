from pathlib import Path
import subprocess,json
r=Path('/yimin/zlc/molclaw_type4_20261003')
print('NODE_CONTENTS',[p.name for p in (r/'node').iterdir()])
for p in (r/'node').glob('**/bin/node'):
 print('NODE_BINARY',p,subprocess.getoutput(str(p)+' --version'))
print('PYTHON_BIN',subprocess.getoutput(str(r/'rootfs/opt/conda/bin/python')+' -c "import requests,yaml;print(\"deps_ok\")"'))
print('MOLCLAW_STATUS',(r/'status.json').read_text()[:1800])
print('MODEL_CONFIG_PRESENT',(r/'private/model.env').exists())
print('EXISTING_UPSTREAM',[p.name for p in (r/'upstream/agent_harness').glob('*.py')])
print('SOl_ROOT_DIR',Path('/yimin/zlc/sol_pi_type4_20261004').exists())
