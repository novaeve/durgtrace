from pathlib import Path
import subprocess
r=Path('/yimin/zlc/sol_pi_type4_20261004')
code="const s=process.binding('natives')['internal/deps/undici/undici']; for(const pat of [/this\\[kHeadersTimeout\\].*/g,/headersTimeout[^\\n]{0,100}300[^\\n]*/g]) {for(const m of s.matchAll(pat)) console.log(s.slice(Math.max(0,m.index-80),m.index+230));}"
print(subprocess.check_output([str(r/'node/bin/node'),'-e',code],env={'OPENSSL_CONF':'/dev/null'},text=True))
for p in [Path('/usr/share/nodejs/undici/lib/client.js'),Path('/usr/share/nodejs/undici/undici-fetch.js')]:
 if p.exists():
  lines=p.read_text().splitlines()
  for i,line in enumerate(lines):
   if 'headersTimeout' in line and ('300' in line or 'headersTimeout =' in line):print('SOURCE',str(p),i+1,'\n'.join(lines[max(0,i-2):i+4]))
