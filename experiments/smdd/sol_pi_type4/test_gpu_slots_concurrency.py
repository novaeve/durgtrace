"""Exercise real flock compatibility with existing workers without launching GPU jobs."""
from pathlib import Path
import importlib.util,importlib.machinery,fcntl,tempfile,time,subprocess

def main(source):
 spec=importlib.util.spec_from_file_location('slots_test',source,loader=importlib.machinery.SourceFileLoader('slots_test',str(source)));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 with tempfile.TemporaryDirectory(prefix='solpi_slot_probe_') as temp:
  root=Path(temp);mod.ROOT=root/'sol';mod.ROOT.mkdir();mod.MOL=root/'mol';shared=mod.MOL/'gpu_locks';shared.mkdir(parents=True)
  mod.subprocess=type('FakeQuery',(),{'check_output':staticmethod(lambda args,**kwargs:'0, 81920\n1, 81920\n' if '-i' not in args else '81920\n')})
  mod.shutil=type('FakeDisk',(),{'disk_usage':staticmethod(lambda path:type('Disk',(),{'free':100*1024**3})())})
  class Clock:
   def __init__(self):self.wall=1000;self.monotonic_time=0
   def monotonic(self):return self.monotonic_time
   def time(self):return self.wall
   def sleep(self,n):self.monotonic_time+=n;self.wall+=n
  mod.time=Clock()
  handles=[]
  def hold(path):
   path.parent.mkdir(parents=True,exist_ok=True);f=path.open('a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);handles.append(f)
  # Old SoL worker owns both its legacy lock and a shared slot on GPU 0.
  hold(mod.ROOT/'gpu_locks/gpu0.sol.lock');hold(shared/'gpu0.slot0.lock')
  hold(shared/'gpu1.slot0.lock');hold(shared/'gpu1.slot1.lock')
  with mod.acquire(root/'first',wait_seconds=2) as (gpu,fds):
   assert gpu==0 and len(fds)==1
   mod.time.wall+=90
   try:
    with mod.acquire(root/'overflow',wait_seconds=2):raise AssertionError('Third lease on a full GPU was admitted')
   except TimeoutError:pass
  for f in handles:f.close()
  mod.time.wall+=90
  with mod.acquire(root/'released',wait_seconds=2) as (gpu,fds):assert gpu in (0,1)
  print('PASS: respects old shared lease, fills second slot, rejects overflow, releases slots')

if __name__=='__main__':
 import sys
 main(sys.argv[1])
