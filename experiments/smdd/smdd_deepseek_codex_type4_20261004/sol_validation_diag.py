from pathlib import Path
import subprocess,os
print((Path('/data2/chenfuxin/sol_pi_type4_20261004')/'source_validation.log').read_text()[-3000:])
print('NODE_NPM',subprocess.getoutput('command -v npm; ls -l /opt/codex-node/bin'))
print('NODE_ENV_KEYS',[k for k in os.environ if any(s in k.upper() for s in ['NPM','NODE','OPENSSL'])])
