from pathlib import Path
import subprocess,json,os
root=Path('/data2/chenfuxin/sol_pi_type4_20261004');sol=Path('/data2/chenfuxin/SoL-Pi')
print('SYMLINKS',[(str(p.relative_to(sol)),os.readlink(p)) for p in sol.glob('node_modules/@earendil-works/*') if p.is_symlink()])
print('SIZE',subprocess.getoutput('du -shL '+str(sol)))
assert json.loads((root/'source_validation.json').read_text())['passed']
with (root/'bundle.log').open('w') as log:
 subprocess.run(['tar','--dereference','-czf',str(root/'sol-pi-runtime.tar.gz'),'-C',str(sol.parent),'SoL-Pi'],stdout=log,stderr=subprocess.STDOUT,check=True)
print('BUNDLE_BYTES',(root/'sol-pi-runtime.tar.gz').stat().st_size)
