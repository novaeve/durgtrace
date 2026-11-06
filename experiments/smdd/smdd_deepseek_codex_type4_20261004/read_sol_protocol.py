from pathlib import Path
import subprocess,json
r=Path('/data2/chenfuxin/SoL-Pi')
print((r/'agents-install.md').read_text())
print('PRIOR_VALIDATION_FILES')
for p in (r.parent/'sol_pi_pmo_20261004').glob('*validation*.json'):print(p.name,p.read_text()[:1800])
print('INSTALL_EVIDENCE',[str(p) for p in r.glob('*validation*')]+[str(p) for p in r.parent.glob('*sol*pi*')])
print('PACKAGES',subprocess.getoutput('/opt/codex-node/bin/node '+str(r/'node_modules/@earendil-works/pi-coding-agent/dist/cli.js')+' --offline list')[-1500:])
