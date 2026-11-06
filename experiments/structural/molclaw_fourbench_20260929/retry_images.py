"""Exactly four authorized image-failure reruns; preserve original full results."""
import concurrent.futures,json,hashlib,fcntl,shutil,time
from pathlib import Path
import run
STAGE='image_retry_20261002'
IDS=['s2_MolEdit_AddComponent_0016','s2_MolEdit_AddComponent_0203','s2_MolEdit_AddComponent_0479','s2_MolEdit_DelComponent_0010']
selected=[c for c in run.cases() if c['id'] in IDS]
assert len(selected)==4
original_popen=run.subprocess.Popen

def guarded_popen(command,**kwargs):
    work=Path(command[command.index('--bind')+1])
    shutil.copyfile(run.ROOT/'image_read_guard.py',work/'image_read_guard.py')
    run.dump(work/'image_guard_settings.json',{'hooks':{'PreToolUse':[{'matcher':'Read','hooks':[{'type':'command','command':'python /workspace/image_read_guard.py','timeout':10}]}]}})
    return original_popen(command+['--settings','/workspace/image_guard_settings.json'],**kwargs)

def main():
    folder=run.ROOT/'runs'/STAGE;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'retry.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before={c['id']:run.sha(run.ROOT/'runs/full'/c['id']/'result.json') for c in selected}
        run.dump(folder/'config.json',{'ids':IDS,'started':time.time(),'change':'PreToolUse Read rejects corrupted PNG; regenerate original image or continue from SMILES','model':run.MODEL,'temperature':0,'output_token_limit':'unchanged','original_result_hashes':before,'code_hashes':{n:run.sha(run.ROOT/n) for n in ['run.py','image_read_guard.py','retry_images.py']}})
        run.subprocess.Popen=guarded_popen
        service=run.gateway()
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(run.job,c,STAGE,service.server_address[1]) for c in selected]
                for f in concurrent.futures.as_completed(futures):f.result();run.summary(STAGE,selected)
        finally:service.shutdown();run.subprocess.Popen=original_popen
        assert all(run.sha(run.ROOT/'runs/full'/k/'result.json')==v for k,v in before.items())
        import score
        score.cases=lambda:selected
        score.main(STAGE)

if __name__=='__main__':main()
