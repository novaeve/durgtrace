"""Durable per-case native runners, configurable concurrency, fixed denominator."""
import collections, concurrent.futures, fcntl, hashlib, importlib.util, json, os
from pathlib import Path
import sys,time,traceback
from common import ROOT,score,dump
METHOD=json.loads((ROOT/'manifest.json').read_text())['method']
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
if METHOD=='MolLingo':
    sys.path.insert(0,'/data2/chenfuxin/molingo_20260922');sys.path.insert(0,str(ROOT))
    native=load(ROOT/'lingo_native.py','lingo_native')
    native.r.CACHE=ROOT/'cache'
    native.r.NAMES=json.loads((ROOT/'cache/names.json').read_text()) if (ROOT/'cache/names.json').exists() else {}
    native.r.STRUCTURES={}
    run_case=lambda c:native.run_case(c,'full')
    nativepath=lambda c:ROOT/'native/MolLingo/full'/c['id']/'result.json'
else:
    native=load(ROOT/'claw_native.py','claw_native')
    run_case=lambda c:native.run_case(c,'full')
    nativepath=lambda c:ROOT/'native/MolClaw/full'/c['id']/'result.json'
CASES=list(reversed(json.loads((ROOT/'cases.json').read_text())))
assert len(CASES)==len({c['id'] for c in CASES})==5600
def fp(c):return ROOT/'runs'/c['id']/'result.json'
def execute(c):
    lockpath=ROOT/'locks'/(c['id']+'.lock');lockpath.parent.mkdir(exist_ok=True)
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if fp(c).exists():return json.loads(fp(c).read_text())
        dump(ROOT/'started'/(c['id']+'.json'),dict(time=time.time(),pid=os.getpid(),case_id=c['id']))
        try:
            run_case(c);row=json.loads(nativepath(c).read_text())
        except Exception as exc:
            row=dict(id=c['id'],status='error',candidate=None,error=type(exc).__name__)
            dump(ROOT/'errors'/(c['id']+'.json'),dict(traceback=traceback.format_exc()))
        row.update(id=c['id'],case=c,method=METHOD,model='deepseek-v4.1-flash',native_result=str(nativepath(c)))
        row['score']=score(c,row.get('candidate') if row.get('status')=='complete' else None)
        dump(fp(c),row)
        return row
def summarize(rows,phase,workers):
    rows.update({r['id']:r for r in (json.loads(p.read_text()) for p in (ROOT/'runs').glob('*/result.json'))})
    groups={}
    for c in CASES:
        key=str(c['task'])+'_'+c['constraint'];groups.setdefault(key,dict(expected=0,processed=0,success=0));groups[key]['expected']+=1
    for row in rows.values():
        key=str(row['case']['task'])+'_'+row['case']['constraint'];groups[key]['processed']+=1;groups[key]['success']+=bool(row['score']['success'])
    out=dict(method=METHOD,phase=phase,expected=5600,processed=len(rows),success=sum(bool(r['score']['success']) for r in rows.values()),
        statuses=dict(collections.Counter(r['status'] for r in rows.values())),reused=sum(bool(r.get('reused_from')) for r in rows.values()),
        errors=dict(collections.Counter(r.get('error','') for r in rows.values() if r['status']!='complete')),groups=groups,workers=workers,updated=time.time())
    out['success_rate_full']=out['success']/5600
    dump(ROOT/'summary_extra.json',out);return out
def batch(selected,rows,phase):
    config=json.loads((ROOT/'concurrency_extra.json').read_text());limit=int(config['workers']);maximum=int(config['maximum'])
    pending=iter(selected);futures={};seen_completed=0;last=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=maximum) as pool:
        while True:
            config=json.loads((ROOT/'concurrency_extra.json').read_text());limit=max(1,min(maximum,int(config['workers'])))
            while len(futures)<limit:
                c=next(pending,None)
                if c is None:break
                futures[pool.submit(execute,c)]=c['id']
            if not futures:break
            done,_=concurrent.futures.wait(futures,timeout=10,return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                case_id=futures.pop(f);rows[case_id]=f.result();seen_completed+=1
            if time.time()-last>15 or not futures:
                summary=summarize(rows,phase,limit);print(json.dumps({k:summary[k] for k in ['method','phase','processed','success','statuses','workers']}),flush=True);last=time.time()
    return rows
def main():
    while not (ROOT/'pilot_gate.json').exists():
        if (ROOT/'exit.json').exists():raise RuntimeError('PRIMARY_STOPPED_BEFORE_PILOT_GATE')
        time.sleep(5)
    assert json.loads((ROOT/'pilot_gate.json').read_text())['accepted']
    lockpath=ROOT/'driver_extra.lock'
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=json.loads((ROOT/'manifest.json').read_text())
        assert hashlib.sha256((ROOT/'cases.json').read_bytes()).hexdigest()==manifest['cases_sha256']
        rows={r['id']:r for r in (json.loads(p.read_text()) for p in (ROOT/'runs').glob('*/result.json'))}
        buckets={}
        for c in CASES:buckets.setdefault((c['task'],c['constraint']),c)
        pilot=list(buckets.values());assert len(pilot)==28
        if not (ROOT/'pilot_gate.json').exists():
            batch([c for c in pilot if c['id'] not in rows],rows,'pilot')
            failures=[dict(id=c['id'],status=rows[c['id']]['status'],error=rows[c['id']].get('error')) for c in pilot if rows[c['id']]['status']!='complete']
            dump(ROOT/'pilot_gate.json',dict(accepted=not failures,episodes=28,failures=failures,time=time.time(),policy='Infrastructure only; valid chemistry failures remain failures; pilot reused in full'))
            if failures:raise RuntimeError('PILOT_INFRASTRUCTURE_FAILURES')
        assert json.loads((ROOT/'pilot_gate.json').read_text())['accepted']
        gate=json.loads((ROOT/'pilot_gate.json').read_text());pilot_ids=set(gate.get('pilot_ids',[]))
        batch([c for c in CASES if c['id'] not in rows and c['id'] not in pilot_ids],rows,'full')
        while len(rows)<5600:
            summarize(rows,'waiting_for_primary_pilot_or_full',json.loads((ROOT/'concurrency_extra.json').read_text())['workers'])
            if len(rows)<5600:time.sleep(15)
        out=summarize(rows,'complete',json.loads((ROOT/'concurrency_extra.json').read_text())['workers'])
        assert len(rows)==5600
        dump(ROOT/'exit_extra.json',dict(success=True,time=time.time(),statuses=out['statuses']))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        dump(ROOT/'exit_extra.json',dict(success=False,time=time.time(),error=type(exc).__name__,traceback=traceback.format_exc()));raise
