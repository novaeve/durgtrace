from pathlib import Path
import json,re,os,collections
root=Path('/yimin/zlc/molclaw_type4_20261003/gpu_locks')
wanted={}
for p in root.glob('gpu*.slot*.lock'):
 st=p.stat();wanted[(os.major(st.st_dev),os.minor(st.st_dev),st.st_ino)]=p.name
counts=collections.Counter()
for line in Path('/proc/locks').read_text().splitlines():
 fields=line.split();dev=next((v for v in fields if re.fullmatch(r'[0-9a-f]+:[0-9a-f]+:\d+',v)),None)
 if not dev:continue
 ma,mi,inode=dev.split(':');name=wanted.get((int(ma,16),int(mi,16),int(inode)))
 if name:
  counts[name.split('.')[0]]+=1;print('LEASE',name,line)
print('HELD_SLOTS',dict(counts));assert all(n<=2 for n in counts.values())
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:args=(proc/'cmdline').read_bytes().decode().split(chr(0))
 except (OSError,UnicodeError):continue
 if 'boltz.main' not in args:continue
 inputs=[arg for arg in args if '/sol_pi_type4_20261004/' in arg and arg.endswith('.yaml')]
 if inputs:
  print('BOLTZ_PROCESS',proc.name,inputs)
  out=Path(args[args.index('--out_dir')+1])
  log=out/'boltz.log'
  if not log.exists():log=out.parent/'boltz.log'
  if log.exists():print('STAGE',log.read_text(errors='replace')[-850:])
