"""Finish current deployment after the running asset transfer, without API keys."""
import json,time,traceback
import remote
DEST='/yimin/zlc/molclaw_type4_20261003'
status=remote.ROOT/'environment_status.json'
def report(**kw):
 status.write_text(json.dumps(dict(time=time.time(),**kw),indent=2));print(json.dumps(kw),flush=True)
try:
 report(status='waiting_for_asset_transfer')
 deadline=time.time()+8*3600
 while time.time()<deadline:
  try:state=json.loads((remote.ROOT/'transfer_status.json').read_text())
  except (FileNotFoundError,ValueError):state={}
  if all(x in state for x in ['rootfs','boltz_cache']):break
  time.sleep(30)
 else:raise TimeoutError('Asset transfer did not finish within 8 hours')
 report(status='running_environment_preflight')
 c=remote.connect();s=c.open_sftp()
 for name in ['preflight.py','preflight_boltz.py','MODEL_ALIGNMENT.json','DEPLOYMENT.md']:
  s.put(str(remote.ROOT/name),DEST+'/'+name)
 s.close()
 remote.run(c,'cd '+DEST+' && PYTHONNOUSERSITE=1 ./proxy_env/bin/python preflight.py',timeout=600)
 report(status='running_boltz_preflight')
 remote.run(c,'cd '+DEST+' && PYTHONNOUSERSITE=1 ./proxy_env/bin/python preflight_boltz.py',timeout=1500)
 c.close();report(status='environment_ready_model_authentication_and_smoke_pending')
except Exception as exc:
 report(status='environment_preflight_failed',error=str(exc));traceback.print_exc();raise
