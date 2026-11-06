"""Read-only result auditing; writes only new experiment summary artifacts."""
import ast,collections,fcntl,hashlib,json,sys,time,traceback
from pathlib import Path
ROOT=Path('/data/chenfuxin/chatdrug_prompt_aligned_full4_bailian_20261011')
REFERENCE=Path('/data2/chenfuxin/chatdrug_prompt_aligned_bailian_20261006/cases.json')
EXPECTED_SHA='d118b671cfa62b74f5366eddbd2296e3c23fb7f0ac59f1ed49e4cb62aeefdccf'
assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest()==EXPECTED_SHA
CASES={c['id']:c for c in json.loads(REFERENCE.read_text())}
assert len(CASES)==5600
METHODS={'MolLingo_single':('molingo','runs'),'MolClaw':('molclaw','runs'),'SoL-pi':('sol_pi','evaluated'),'Codex':('codex','evaluated')}
CACHE={};AUDITS={}

def dump(path,obj):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));temp.replace(path)

def inspect(path):
 stat=path.stat();stamp=(stat.st_mtime_ns,stat.st_size)
 if path in CACHE and CACHE[path][0]==stamp:return CACHE[path][1]
 r=json.loads(path.read_text());case_id=r['id'];assert case_id in CASES,case_id
 assert path.parent.name==case_id
 c=r['case'];assert all(c.get(k)==v for k,v in CASES[case_id].items()),str(path)
 s=r['score'];assert isinstance(s['success'],bool) and isinstance(s['valid'],bool)
 short=dict(id=case_id,status=r['status'],success=s['success'],valid=s['valid'],reused=bool(r.get('reused') or r.get('reused_from')))
 CACHE[path]=(stamp,short);return short

def final_audit(method,paths):
 chat=Path('/data2/chenfuxin/chatdrug_generalization_20260920')
 sys.path.insert(0,str(chat));import pilot as p
 from rdkit import rdBase,RDLogger
 RDLogger.DisableLog('rdApp.*');assert rdBase.rdkitVersion=='2022.09.4'
 node=next(n for n in ast.parse((chat/'full_experiment.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='score')
 ns={'p':p};exec(compile(ast.Module(body=[node],type_ignores=[]),'original_score','exec'),ns)
 h=hashlib.sha256();groups=collections.defaultdict(collections.Counter);issues=[]
 for path in sorted(paths):
  raw=path.read_bytes();h.update(str(path).encode()+b'\0'+raw+b'\0')
  r=json.loads(raw);c=CASES[r['id']];candidate=r.get('candidate') if r['status']=='complete' else None
  score=ns['score'](dict(c,thresholds=[0]*len(c['objectives'])),candidate)
  if any(score[k]!=r['score'][k] for k in ['valid','success']):issues.append(r['id'])
  for group in ['all',str(c['task']),str(c['task'])+'_'+c['constraint'],'single' if len(c['objectives'])==1 else 'multi']:
   groups[group].update(n=1,valid=score['valid'],success=score['success'])
 result=dict(method=method,checked=5600,rdkit=rdBase.rdkitVersion,passed=not issues,issues=issues,result_bytes_sha256=h.hexdigest(),groups={k:dict(v,rate=v['success']/v['n']) for k,v in groups.items()},time=time.time())
 dump(ROOT/(METHODS[method][0]+'_final_audit.json'),result)
 assert not issues,(method,issues[:10])
 return result

def main():
 with (ROOT/'aggregate.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while True:
   report=dict(expected_per_method=5600,expected_total=22400,reference_sha256=EXPECTED_SHA,methods={},time=time.time())
   for method,(sub,leaf) in METHODS.items():
    paths=list((ROOT/sub/leaf).glob('*/result.json'));rows=[inspect(path) for path in paths]
    assert len({r['id'] for r in rows})==len(rows)<=5600
    item=dict(processed=len(rows),complete=sum(r['status']=='complete' for r in rows),statuses=dict(collections.Counter(r['status'] for r in rows)),reused=sum(r['reused'] for r in rows),success=sum(r['success'] for r in rows),valid=sum(r['valid'] for r in rows))
    if len(rows)==5600:
     if method not in AUDITS:AUDITS[method]=final_audit(method,paths)
     item.update(final_success_rate=AUDITS[method]['groups']['all']['rate'],final_audit_passed=AUDITS[method]['passed'])
    report['methods'][method]=item
   report['processed_total']=sum(m['processed'] for m in report['methods'].values())
   report['all_finished']=len(AUDITS)==4
   dump(ROOT/'aggregate_status.json',report)
   print(json.dumps({'time':report['time'],'processed_total':report['processed_total'],'all_finished':report['all_finished']}),flush=True)
   if report['all_finished']:
    dump(ROOT/'final_summary.json',dict(report,audits=AUDITS));return
   time.sleep(60)

if __name__=='__main__':
 try:main()
 except Exception as exc:
  dump(ROOT/'aggregate_error.json',dict(error=type(exc).__name__,traceback=traceback.format_exc(),time=time.time()));raise
