import remote,sys,time,concurrent.futures
sys.path.insert(0,str(remote.ROOT.parent/'gpu-scheduling-20261001'))
import manage
SIZE=8*1024*1024
def source():
 c=manage.connect('gpu');t=time.monotonic()
 _,o,e=c.exec_command('head -c 8388608 /data2/chenfuxin/boltz-cache/boltz2_conf.ckpt',timeout=120)
 data=o.read();elapsed=time.monotonic()-t;c.close()
 return {'link':'5090_to_local_ssh_stream','bytes':len(data),'seconds':round(elapsed,2),'mib_s':round(len(data)/1048576/elapsed,2)}
def destination():
 c=remote.connect();t=time.monotonic()
 i,o,e=c.exec_command('cat > /dev/null',timeout=120)
 block=b'X'*1048576
 for _ in range(8):i.write(block)
 i.channel.shutdown_write();rc=o.channel.recv_exit_status();elapsed=time.monotonic()-t;c.close()
 return {'link':'local_to_A100_ssh_stream','bytes':SIZE,'seconds':round(elapsed,2),'mib_s':round(SIZE/1048576/elapsed,2),'exit':rc}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
 for f in [ex.submit(source),ex.submit(destination)]:print(f.result(),flush=True)
