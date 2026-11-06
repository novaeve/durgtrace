from pathlib import Path
import json
r=Path('/data2/chenfuxin/sol_pi_type4_20261004')
print('PREFLIGHT',(r/'preflight.log').read_text()[-3500:])
for p in r.glob('preflight/*/*.json'):print('FILE',str(p.relative_to(r)),p.read_text()[:1000])
for p in r.glob('preflight/solpi/*/stderr.log'):print('STDERR',p.read_text()[-1300:])
for p in r.glob('preflight/solpi/*/result.json'):print('RESULT',p.read_text())
