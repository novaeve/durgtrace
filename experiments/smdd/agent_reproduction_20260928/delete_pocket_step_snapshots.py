"""Delete only user-authorized numbered Pocket2Mol snapshots, with audit list."""
from pathlib import Path
import datetime
import json
import re
import shutil

ROOT=Path('/data2/chenfuxin/liddia_smdd_type4_20260928/runs').resolve(strict=True)
assert str(ROOT)=='/data2/chenfuxin/liddia_smdd_type4_20260928/runs'
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ')
    except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    if b'python' in cmd and any(x in cmd for x in (b'run_type4_batch.py',b'run_liddia_type4.py',b'sample_for_pdb.py',b'pocket_runtime.py')):
        raise RuntimeError('An experiment process may be using snapshots: '+proc.name)
targets=[]
for p in ROOT.rglob('samples_*.pt'):
    if not re.fullmatch(r'samples_\d+\.pt',p.name):continue
    if p.is_symlink() or not p.is_file():continue
    resolved=p.resolve(strict=True)
    rel=resolved.relative_to(ROOT)
    parts=rel.parts
    if 'generation' not in parts:continue
    i=parts.index('generation')
    if len(parts)<=i+4 or not parts[i+1].startswith('pocket_') or parts[i+2]!='output':continue
    stat=p.stat()
    targets.append({'path':str(resolved),'bytes':stat.st_size,'inode':stat.st_ino})
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
audit=ROOT.parent/('snapshot_cleanup_'+stamp+'.json')
before=shutil.disk_usage(ROOT).free
record={'pattern':'generation/pocket_*/output/**/samples_[0-9]+.pt','targets':targets,
        'count':len(targets),'bytes':sum(x['bytes'] for x in targets),'free_before':before,'status':'planned'}
audit.write_text(json.dumps(record,indent=2))
deleted=0
try:
    for item in targets:
        p=Path(item['path'])
        if p.is_symlink() or p.resolve(strict=True).is_relative_to(ROOT) is False:
            raise RuntimeError('Path changed: '+str(p))
        stat=p.stat()
        if stat.st_ino!=item['inode'] or stat.st_size!=item['bytes']:
            raise RuntimeError('File changed: '+str(p))
        p.unlink()
        deleted+=1
    record['status']='complete'
finally:
    record.update(deleted=deleted,free_after=shutil.disk_usage(ROOT).free)
    audit.write_text(json.dumps(record,indent=2))
print(json.dumps({k:v for k,v in record.items() if k!='targets'}))
print('audit='+str(audit))
