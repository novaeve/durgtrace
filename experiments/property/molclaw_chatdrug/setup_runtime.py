import ast,hashlib,json,os,pathlib,shutil,subprocess,sys,time
R=pathlib.Path(sys.argv[1]);B=R/'bundle';original='/data2/chenfuxin/molclaw_20260924'
hashes=json.loads((B/'bundle_hashes.json').read_text());bad=[]
for rel,h in hashes.items():
 p=B/rel
 if hashlib.sha256(p.read_bytes()).hexdigest()!=h:bad.append(rel)
assert not bad,bad[:10]
envdir=B/'isolated_env';py=envdir/'bin/python'
for n in ['python','python3','python3.10']:
 p=envdir/'bin'/n
 if p.is_symlink():p.unlink()
 if not p.exists():p.symlink_to(B/'pythonroot/bin/python3.10')
(envdir/'pyvenv.cfg').write_text('home = '+str(B/'pythonroot/bin')+'\ninclude-system-site-packages = false\nversion = 3.10.12\n')
for p in (envdir/'bin').iterdir():
 if not p.is_file() or p.is_symlink():continue
 data=p.read_bytes()
 if data.startswith(b'#!'):
  first,sep,rest=data.partition(b'\n')
  if b'python' in first:p.write_bytes(b'#!'+str(py).encode()+b'\n'+rest)
env=dict(os.environ,PATH=str(B/'node/bin')+':'+str(envdir/'bin')+':'+os.environ.get('PATH',''),LD_LIBRARY_PATH=str(B/'node/lib')+':'+os.environ.get('LD_LIBRARY_PATH',''),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENSSL_CONF='/dev/null')
def check(cmd):
 q=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=60)
 if q.returncode:raise RuntimeError('Runtime check failed: '+q.stderr[-1800:])
 return q.stdout.strip()
versions=check([str(py),'-c','import json,sys,rdkit,ssl,litellm;print(json.dumps(dict(python=sys.version,rdkit=rdkit.__version__,ssl=ssl.OPENSSL_VERSION)))'])
cli=check([str(B/'runtime/node_modules/.bin/claude'),'--version'])
assert json.loads(versions)['rdkit']=='2022.09.5';assert '2.1.281' in cli,cli
agent=(B/'claw_agent.py').read_text().replace("pathlib.Path('/data2/chenfuxin/molclaw_20260924')",'pathlib.Path('+repr(str(B))+')').replace("pathlib.Path('/data/chenfuxin/chatdrug_prompt_aligned_full4_bailian_20261011/molclaw')",'pathlib.Path('+repr(str(R))+')')
assert original not in agent
(R/'claw_agent.py').write_text(agent);shutil.copy2(B/'cases.json',R/'cases.json');shutil.copy2(B/'claw_native.py',R/'claw_native_original.py')
proxy=(B/'launch_proxy.py').read_text().replace("pathlib.Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env')",'pathlib.Path('+repr(str(B/'private/bailian.env'))+')').replace("'/data2/chenfuxin/molclaw_20260924/isolated_env/bin/litellm'",repr(str(envdir/'bin/litellm')))
(R/'launch_proxy.py').write_text(proxy)
with (R/'proxy.log').open('ab') as log:p=subprocess.Popen([str(py),'-u',str(R/'launch_proxy.py')],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(R/'proxy.pid').write_text(str(p.pid))
record=dict(time=time.time(),verified_files=len(hashes),versions=json.loads(versions),cli=cli,source_agent_sha=hashlib.sha256((B/'claw_agent.py').read_bytes()).hexdigest(),remote_agent_sha=hashlib.sha256(agent.encode()).hexdigest(),cases_sha256=hashlib.sha256((R/'cases.json').read_bytes()).hexdigest(),proxy_pid=p.pid,relocations_only=True)
(R/'runtime_validation.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
