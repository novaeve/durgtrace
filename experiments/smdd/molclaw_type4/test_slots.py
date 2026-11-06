"""Exercise real Linux flock contention without reserving a physical GPU."""
import multiprocessing as mp,tempfile,time
from pathlib import Path
import gpu_slots
def worker(root,queue,index):
 gpu_slots.ROOT=Path(root)
 gpu_slots.ADMISSION_COOLDOWN=0;gpu_slots.POLL_SECONDS=.02
 gpu_slots.subprocess.check_output=lambda *a,**k:'0, 80000\n1, 80000\n'
 out=Path(root)/str(index);out.mkdir()
 with gpu_slots.acquire(out,wait_seconds=10) as gpu:
  queue.put(('start',gpu,time.monotonic()));time.sleep(.4);queue.put(('end',gpu,time.monotonic()))
if __name__=='__main__':
 with tempfile.TemporaryDirectory() as root:
  queue=mp.Queue();workers=[mp.Process(target=worker,args=(root,queue,i)) for i in range(6)]
  for p in workers:p.start()
  events=[queue.get(timeout=15) for _ in range(12)]
  for p in workers:p.join(5);assert p.exitcode==0
  active=[0,0];peak=[0,0];total=0
  for kind,gpu,_ in sorted(events,key=lambda e:e[2]):
   active[gpu]+=1 if kind=='start' else -1
   assert 0<=active[gpu]<=2
   peak[gpu]=max(peak[gpu],active[gpu]);total=max(total,sum(active))
  assert peak==[2,2] and total==4 and active==[0,0],(peak,total,active)
  print('PASS: six contenders, max two per GPU, four overall; remaining workers waited and completed')
