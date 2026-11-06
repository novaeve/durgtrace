"""Host-side SSH transport; one GPU job at a time, official Boltz settings."""
import json,os,pathlib,shlex,subprocess,time,uuid,yaml
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-i','/home/chenfuxin/.ssh/smdd_gpu2','-p','17065','chenfuxin@123.157.219.189']
SCP=['scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-i','/home/chenfuxin/.ssh/smdd_gpu2','-P','17065']

def transfer(cmd,check=True):
    for attempt in range(3):
        try:
            result=subprocess.run(cmd,capture_output=True,timeout=300)
            if result.returncode==0: return result
        except subprocess.TimeoutExpired:
            if attempt==2:raise
        if attempt<2:time.sleep(2*(attempt+1))
    if check:result.check_returncode()
    return result

def predict(payload,out,samples=10,seed=42):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    job='chatdrug_type4_'+uuid.uuid4().hex[:12]
    remote='/data2/chenfuxin/smdd_boltz_jobs/'+job
    inputpath=out/'input.yaml';inputpath.write_text(yaml.safe_dump(payload))
    transfer(SSH+['mkdir -p '+shlex.quote(remote)])
    transfer(SCP+[str(inputpath),'chenfuxin@123.157.219.189:'+remote+'/input.yaml'])
    command='/usr/bin/python3 /data2/chenfuxin/smdd_type4_full340_bailian_20260929/gpu_pool.py '+shlex.quote(remote)+' --samples '+str(int(samples))+' --seed '+str(int(seed))
    (out/'provenance.json').write_text(json.dumps({'remote_job':remote,'gpu_pool':[0,5,7],'samples':samples,'seed':seed,'command':command},indent=2))
    for attempt in range(3):
        result=subprocess.run(SSH+[command],capture_output=True,text=True,timeout=7350)
        if result.returncode!=255:break
        if attempt<2:time.sleep(3)
    transfer(SCP+['chenfuxin@123.157.219.189:'+remote+'/gpu_lease.json',str(out/'gpu_lease.json')],check=False)
    transfer(SCP+['chenfuxin@123.157.219.189:'+remote+'/boltz.log',str(out/'boltz.log')],check=False)
    if result.returncode:raise RuntimeError('REMOTE_BOLTZ_EXIT_'+str(result.returncode))
    (out/'prediction').mkdir(exist_ok=True)
    transfer(SCP+['-r','chenfuxin@123.157.219.189:'+remote+'/out/boltz_results_input/.',str(out/'prediction')])
    affinity=out/'prediction/predictions/input/affinity_input.json'
    return json.loads(affinity.read_text())
