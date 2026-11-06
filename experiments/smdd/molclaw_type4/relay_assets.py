"""Local SSH stream relay: no API secrets or SSH keys are copied between hosts."""
import sys,pathlib,shlex,time,json,threading
import remote
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
DEST='/yimin/zlc/molclaw_type4_20261003'
assets=[
 ('/data2/chenfuxin/molclaw_20260924/runtime','cli_runtime'),
 ('/opt/codex-node','node'),
 ('/data2/chenfuxin/molclaw_20260924/source/MolClaw-main','molclaw_source'),
 ('/data2/chenfuxin/molclaw_20260924/isolated_env','proxy_env'),
 ('/data2/chenfuxin/smdd_type3_transfer_20260930/upstream','upstream'),
 ('/data2/chenfuxin/liddia_smdd_type4_20260928/benchmark/tasks','tasks'),
 ('/data2/chenfuxin/liddia_smdd_type4_20260928/evaluator_rootfs','rootfs'),
 ('/data2/chenfuxin/boltz-cache','boltz_cache')]
state_path=remote.ROOT/'transfer_status.json'
state=json.loads(state_path.read_text()) if state_path.exists() else {}
for source,name in assets:
 if name in state:continue
 old=manage.connect('gpu');new=remote.connect()
 old.get_transport().set_keepalive(15)
 exclusions=' --exclude=./root/.boltz' if name=='rootfs' else (' --exclude=./mols.tar' if name=='boltz_cache' else '')
 command='nice -n 15 tar --exclude=__pycache__ --exclude=.git'+exclusions+' -czf - -C '+shlex.quote(source)+' .'
 _,out,err=old.exec_command(command,timeout=3600)
 stdin,dout,derr=new.exec_command('mkdir -p '+shlex.quote(DEST+'/'+name)+' && tar --no-same-owner -xzf - -C '+shlex.quote(DEST+'/'+name),timeout=3600)
 error=[]
 def drain(stream,label):
  data=stream.read().decode(errors='replace')
  if data:error.append(label+': '+data[-3000:])
 threads=[threading.Thread(target=drain,args=(err,'source'),daemon=True),threading.Thread(target=drain,args=(derr,'destination'),daemon=True)]
 for t in threads:t.start()
 size=0;start=time.time();last=start;print('START',name,flush=True)
 while True:
  block=out.read(1024*1024)
  if not block:break
  stdin.write(block);size+=len(block)
  if time.time()-last>30:
   print('PROGRESS',name,round(size/1024**2),'MiB',round(size/(time.time()-start)/1024**2,1),'MiB/s',flush=True);last=time.time()
 stdin.channel.shutdown_write()
 code=out.channel.recv_exit_status();destination_code=dout.channel.recv_exit_status()
 for t in threads:t.join(5)
 if code or destination_code:raise RuntimeError(str((code,destination_code,error)))
 state[name]=dict(compressed_bytes=size,seconds=time.time()-start);state_path.write_text(json.dumps(state,indent=2))
 print('DONE',name,round(size/1024**2),'MiB',flush=True);old.close();new.close()
old=manage.connect('gpu');s=old.open_sftp()
for src,name in [('/data2/chenfuxin/smdd_type3_harness_20261001/run.py','source_run.py'),('/data2/chenfuxin/smdd_type3_transfer_20260930/runtime.py','source_runtime.py'),('/data2/chenfuxin/smdd_type3_transfer_20260930/evaluate.py','source_evaluate.py'),('/data2/chenfuxin/smdd_type3_transfer_20260930/eval_bridge.py','eval_bridge.py')]:s.get(src,str(remote.ROOT/name))
s.close();old.close();print('ALL_ASSETS_READY',flush=True)
