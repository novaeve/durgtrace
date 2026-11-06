import concurrent.futures,fcntl,json,datetime
import runner as r

stage=r.ROOT/'runs/full'
lock=(stage/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
cfg=json.loads((stage/'run_config.json').read_text())
assert all(r.p.sha(r.ROOT/n)==h for n,h in cfg['code_hashes'].items())
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
archive=r.ROOT/'archives'/('transport_retry_'+stamp);archive.mkdir(parents=True)
cases=[]
for file in sorted(stage.glob('*/result.json')):
 row=json.loads(file.read_text())
 if row['status']=='error' and row.get('error')=='TRANSPORT_ERROR':cases.append((file.parent,row['case']))
assert len(cases)==86,len(cases)
for name in ['summary.json','audit.json']:
 (archive/name).write_bytes((stage/name).read_bytes())
for path,case in cases:path.rename(archive/path.name)
r.dump(archive/'retry_manifest.json',{'case_ids':[c['id'] for _,c in cases],'reason':'transport errors only; model-output failures unchanged','code_hashes':cfg['code_hashes']})
print('Archived and retrying',len(cases),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 jobs=[pool.submit(r.run_case,c,'full') for _,c in cases]
 for job in concurrent.futures.as_completed(jobs):job.result();r.summarize('full')
result=r.summarize('full')
print(json.dumps({'processed':result['processed'],'errors':result['errors']}),flush=True)
if result['errors']:raise SystemExit(2)
