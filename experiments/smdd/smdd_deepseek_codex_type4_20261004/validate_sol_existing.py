from pathlib import Path
import subprocess,os,json,time
r=Path('/data2/chenfuxin/SoL-Pi');out=Path('/data2/chenfuxin/sol_pi_type4_20261004');out.mkdir(exist_ok=True)
env=dict(os.environ,PATH='/opt/codex-node/bin:'+os.environ.get('PATH',''))
for k in ['OPENSSL_CONF','OPENSSL_MODULES']:env.pop(k,None)
env['OPENSSL_CONF']='/dev/null'
commands=[['git','status','--short','--branch'],['git','rev-parse','HEAD'],['node','--version'],['npm','--version'],['npm','run','check'],['npm','audit','--audit-level=high'],['node','scripts/check-pi-compat.mjs'],['node','node_modules/vitest/vitest.mjs','run','tests/all-mechanisms.test.ts']]
with (out/'source_validation.log').open('w') as log:
 for cmd in commands:
  log.write('COMMAND '+json.dumps(cmd)+'\n');log.flush()
  p=subprocess.run(cmd,cwd=r,env=env,stdout=log,stderr=subprocess.STDOUT)
  if p.returncode:raise RuntimeError('SoL-Pi source validation failed: '+str(cmd))
(out/'source_validation.json').write_text(json.dumps({'passed':True,'commands':commands,'version':'existing Pi0.86.1 compatibility install','reason':'reuse installed runtime without npm ci or dependency mutations; full suite rerun','time':time.time()},indent=2))
print('SOURCE_VALIDATION_PASSED')
