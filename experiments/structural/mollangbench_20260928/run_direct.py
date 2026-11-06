"""Public prompts only. Gold answers are accessed only by a separate scorer."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse,concurrent.futures,fcntl,json,time
from pathlib import Path
from transport import Relay,LongTruncation,dump,sha
ROOT=Path(__file__).resolve().parent

def job(case,stage):
 out=ROOT/'runs'/stage/'deepseek'/case['id'];out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 relay=Relay(out);start=time.time()
 result={'id':case['id'],'task':case['task'],'split':case['split'],'index':case['index'],'started':start}
 try:
  raw=relay.complete([{'role':'user','content':case['prompt']}],'deepseek/1')
  result.update(status='complete',output=raw)
 except LongTruncation:
  records=[json.loads(p.read_text()) for p in (out/'api').glob('*.json')]
  raw=next((r['output'] for r in records if r.get('finish_reason')=='length'),'')
  result.update(status='error',error='PROVIDER_OUTPUT_TRUNCATED',output=raw)
 except Exception as e:result.update(status='error',error=type(e).__name__,output='')
 result.update(ended=time.time(),seconds=time.time()-start,usage=relay.usage())
 dump(out/'result.json',result);print(json.dumps({'id':case['id'],'status':result['status']}),flush=True)
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);a=ap.parse_args()
 folder=ROOT/'runs'/a.stage/'deepseek';folder.mkdir(parents=True,exist_ok=True)
 lock=(folder/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cases=json.loads((ROOT/'data/cases.json').read_text())
 if a.stage=='pilot':cases=[c for c in cases if c['index']<2]
 else:
  p=json.loads((ROOT/'runs/pilot/deepseek/summary.json').read_text());assert p['processed']==8
  pilot_rows=[json.loads(p.read_text()) for p in (ROOT/'runs/pilot/deepseek').glob('*/result.json')]
  assert all(r['status']=='complete' or r.get('error')=='PROVIDER_OUTPUT_TRUNCATED' for r in pilot_rows)
 config={'model':'deepseek-v4.1-flash','provider':'Alibaba Bailian','temperature':0,'thinking':False,'max_tokens':None,'workers':4,'case_count':len(cases),'single_generation':True,'prompt':'official SMILES template verbatim','gold_access_during_generation':False,'code_hashes':{p.name:sha(p) for p in [ROOT/'run_direct.py',ROOT/'transport.py']},'manifest_sha256':sha(ROOT/'data/experiment_manifest.json')}
 cp=folder/'config.json'
 if cp.exists():assert json.loads(cp.read_text())==config
 else:dump(cp,config)
 rows={r['id']:r for p in folder.glob('*/result.json') for r in [json.loads(p.read_text())]}
 pending=[c for c in cases if c['id'] not in rows];pending.sort(key=lambda c:(c['index'],c['task'],c['split']))
 def summarize():
  d={'processed':len(rows),'expected':len(cases),'errors':sum(r['status']!='complete' for r in rows.values()),'updated':time.time(),'status':'finished' if len(rows)==len(cases) else 'running'}
  dump(folder/'summary.json',d);return d
 with concurrent.futures.ThreadPoolExecutor(4) as pool:
  fs=[pool.submit(job,c,a.stage) for c in pending]
  for f in concurrent.futures.as_completed(fs):r=f.result();rows[r['id']]=r;summarize()
 print(json.dumps(summarize()),flush=True)

if __name__=='__main__':main()
