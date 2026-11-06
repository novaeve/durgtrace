"""Keep new experiment workers durable and maintain an ID-unique authoritative summary."""
import collections,json,os,subprocess,time,signal,hashlib,urllib.request,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PY='/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python'
def dump(path,obj):
    tmp=path.with_name(path.name+'.supervisor.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.replace(path)
def alive(pid):
    try:
        proc=Path('/proc')/str(pid)
        return (proc/'cwd').resolve()==ROOT and (proc/'stat').read_text().split()[2]!='Z'
    except (FileNotFoundError,ProcessLookupError,PermissionError):return False
def start(role):
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENSSL_CONF='/dev/null')
    env['PATH']='/opt/codex-node/bin:'+env.get('PATH','')
    with (ROOT/(role+'.log')).open('ab') as out:p=subprocess.Popen([PY,'-u',str(ROOT/(role+'.py'))],cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    (ROOT/(role+'.pid')).write_text(str(p.pid));return p.pid
cases=json.loads((ROOT/'cases.json').read_text());expected={c['id'] for c in cases};restarts=collections.Counter();history=[]
last_scale=time.time();last_proxy_position=0;last_rate_error=0;last_proxy_retry=0
def stop_dispatch(reason):
    paused=[]
    for role in ['driver','driver_extra']:
        f=ROOT/(role+'.pid')
        if f.exists() and alive(int(f.read_text())):
            pid=int(f.read_text());os.kill(pid,signal.SIGSTOP);paused.append(pid)
    dump(ROOT/'dispatch_paused.json',dict(time=time.time(),reason=reason,pids=paused,policy='Pause scheduling parent processes only; existing native CLI child processes retained'))
def resume_dispatch():
    p=ROOT/'dispatch_paused.json'
    if p.exists():
        for pid in json.loads(p.read_text())['pids']:
            if alive(pid):os.kill(pid,signal.SIGCONT)
        p.unlink()
def guards():
    m=json.loads((ROOT/'manifest.json').read_text())
    assert hashlib.sha256((ROOT/'cases.json').read_bytes()).hexdigest()==m['cases_sha256'],'CASE_HASH_CHANGED'
    revision=json.loads((ROOT/'parallel_revision.json').read_text())
    for name,digest in revision['source_hashes'].items():
        if name=='supervisor.py':continue
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,'SOURCE_HASH_CHANGED: '+name
    gatepath=ROOT/'pilot_gate.json'
    if gatepath.exists():
        gate=json.loads(gatepath.read_text())
        if not gate.get('accepted'):
            failures=gate.get('failures',[]);content_rejections=[]
            for failure in failures:
                evidence=ROOT/'native/MolClaw/full'/failure['id']/'events.jsonl'
                if evidence.exists() and 'DataInspectionFailed' in evidence.read_text():content_rejections.append(failure['id'])
            if failures and len(content_rejections)==len(failures):
                dump(ROOT/'pilot_provider_rejection_audit.json',dict(original_gate=gate,retained_failed_ids=content_rejections,no_episode_retry=True))
                gate.update(accepted=True,provider_rejections=content_rejections,policy='All infrastructure verified; provider content rejections retained as failures without rerunning');dump(gatepath,gate)
                end=ROOT/'exit.json'
                if end.exists() and not json.loads(end.read_text()).get('success'):end.rename(ROOT/('exit_pilot_provider_rejection_'+str(int(time.time()))+'.json'))
            else:raise RuntimeError('PILOT_INFRASTRUCTURE_OR_SCHEMA_FAILURE')
def change_workers(filename,workers,reason):
    p=ROOT/filename;config=json.loads(p.read_text());before=config['workers']
    if before==workers:return
    config.update(workers=workers,changed=time.time(),reason=reason);dump(p,config)
    history.append(dict(time=time.time(),control=filename,before=before,after=workers,reason=reason))
def supervise():
    global last_scale,last_proxy_position,last_rate_error,last_proxy_retry
    while True:
        guards()
        if json.loads((ROOT/'manifest.json').read_text())['method']=='MolClaw':
            proxyfile=ROOT/'proxy.pid';proxy=int(proxyfile.read_text()) if proxyfile.exists() else None
            if not proxy or not alive(proxy):
                stop_dispatch('Dedicated MolClaw proxy unavailable; restart before further case dispatch')
                if time.time()-last_proxy_retry>60:
                    last_proxy_retry=time.time();proxy=start('launch_proxy');proxyfile.write_text(str(proxy));history.append(dict(time=time.time(),proxy_restarted=proxy))
                port=json.loads((ROOT/'proxy_port.json').read_text())['port'];healthy=False
                for _ in range(20):
                    try:
                        healthy=urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health/liveliness',timeout=2).status==200
                        if healthy:break
                    except Exception:pass
                    time.sleep(1)
                if not healthy:time.sleep(10);continue
                resume_dispatch()
        rows={}
        for f in (ROOT/'runs').glob('*/result.json'):
            r=json.loads(f.read_text());assert r['id'] in expected and r['id']==f.parent.name
            rows[r['id']]=r
        roles={}
        for role,end in [('driver','exit.json'),('driver_extra','exit_extra.json')]:
            pidfile=ROOT/(role+'.pid');pid=int(pidfile.read_text()) if pidfile.exists() else None
            running=bool(pid and alive(pid));roles[role]=dict(pid=pid,running=running)
            if not running and not (ROOT/end).exists() and restarts[role]<3 and len(rows)<5600:
                pid=start(role);restarts[role]+=1;history.append(dict(role=role,pid=pid,time=time.time(),reason='missing worker without terminal marker; existing results and per-case locks retained'))
        errors=collections.Counter(r.get('error','') for r in rows.values() if r['status']!='complete')
        groups={}
        for c in cases:
            k=str(c['task'])+'_'+c['constraint'];groups.setdefault(k,dict(expected=0,processed=0,success=0));groups[k]['expected']+=1
        for r in rows.values():
            k=str(r['case']['task'])+'_'+r['case']['constraint'];groups[k]['processed']+=1;groups[k]['success']+=bool(r['score']['success'])
        out=dict(method=json.loads((ROOT/'manifest.json').read_text())['method'],expected=5600,processed=len(rows),success=sum(bool(r['score']['success']) for r in rows.values()),
            reused=sum(bool(r.get('reused_from')) for r in rows.values()),statuses=dict(collections.Counter(r['status'] for r in rows.values())),errors=dict(errors),
            phase='complete' if len(rows)==5600 else 'running',roles=roles,groups=groups,updated=time.time(),restart_history=history,
            nominal_workers=sum(json.loads((ROOT/f).read_text())['workers'] for f in ['concurrency.json','concurrency_extra.json']))
        out['success_rate_full']=out['success']/5600
        out['active_started_without_final']=sum(f.stem not in rows for f in (ROOT/'started').glob('*.json'))
        method=out['method'];rate_errors=0
        if method=='MolLingo':
            for f in (ROOT/'native').rglob('api_calls.json'):
                if time.time()-f.stat().st_mtime>35:continue
                for call in json.loads(f.read_text()):
                    rate_errors+=sum(a.get('status') in [429,502,503,504] or a.get('error_type') in ['ConnectionError','ReadTimeout','ConnectTimeout','ChunkedEncodingError'] for a in call['attempts'])
        else:
            log=ROOT/'proxy.log'
            if log.exists():
                size=log.stat().st_size
                with log.open('rb') as f:
                    f.seek(max(last_proxy_position,size-200000));recent=f.read().decode('utf-8','replace')
                last_proxy_position=size
                rate_errors=sum(recent.count(x) for x in ['429 Too Many Requests','502 Bad Gateway','503 Service Unavailable','504 Gateway Timeout','APIConnectionError','ConnectTimeout','ReadTimeout'])
        out['recent_rate_or_gateway_errors']=rate_errors
        if rate_errors:last_rate_error=time.time()
        gatepath=ROOT/'pilot_gate.json'
        if method=='MolClaw' and rate_errors==0 and not last_rate_error and gatepath.exists():
            gate=json.loads(gatepath.read_text())
            if gate.get('provisional'):
                remaining=sum(caseid not in rows for caseid in gate['pilot_ids'])
                if remaining:
                    main_active=max(1,min(16,remaining))
                    change_workers('concurrency.json',main_active,'Preserve remaining primary pilot episodes; use auxiliary capacity to maintain48 total')
                    change_workers('concurrency_extra.json',48-main_active,'Fill available slots during provisional pilot long tail; native budgets unchanged')
            elif (ROOT/'provisional_pilot_evidence.json').exists():
                change_workers('concurrency.json',16,'Final28 pilot accepted; restore primary full pool16')
                change_workers('concurrency_extra.json',32,'Final28 pilot accepted;32 auxiliary plus16 primary')
        if rate_errors>=3 and time.time()-last_scale>60:
            for filename in ['concurrency.json','concurrency_extra.json']:
                now=json.loads((ROOT/filename).read_text())['workers'];change_workers(filename,max(1,now//2),'Backoff after repeated provider rate/gateway errors')
            last_scale=time.time()
        elif rate_errors==0 and last_rate_error and time.time()-last_rate_error>120 and time.time()-last_scale>60:
            targets=[32,32] if method=='MolLingo' else [16,32]
            for filename,target in zip(['concurrency.json','concurrency_extra.json'],targets):
                now=json.loads((ROOT/filename).read_text())['workers'];change_workers(filename,min(target,now*2),'Recover gradually after at least120s without provider rate/connection errors')
            last_scale=time.time()
        elif method=='MolClaw' and not errors and rate_errors==0 and (ROOT/'pilot_gate.json').exists() and time.time()-last_scale>60:
            gate=json.loads((ROOT/'pilot_gate.json').read_text());extra=json.loads((ROOT/'concurrency_extra.json').read_text())['workers']
            if gate.get('accepted') and len(rows)>=356 and extra==8:
                change_workers('concurrency_extra.json',16,'Pilot passed and at least8 further cases finished; total32');last_scale=time.time()
            elif gate.get('accepted') and len(rows)>=372 and extra==16:
                change_workers('concurrency_extra.json',32,'Total32 stable and at least24 postpilot cases finished; total48');last_scale=time.time()
        dump(ROOT/'combined_summary.json',out)
        if len(rows)==5600:break
        time.sleep(30)

try:
    supervise()
except Exception:
    stop_dispatch("Supervisor schema/source/runtime guard failed; manual review required")
    dump(ROOT/"supervisor_fatal.json",dict(time=time.time(),traceback=traceback.format_exc()))
    raise
