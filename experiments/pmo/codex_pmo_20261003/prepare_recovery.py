from pathlib import Path
import json,fcntl,time,shutil,hashlib
ROOT=Path(__file__).resolve().parent
archive=ROOT/'recovery_20261004'
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2))
with (ROOT/'full.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (archive/'manifest.json').exists(),'Recovery already prepared'
    plans=[];completed={}
    for out in sorted((ROOT/'control/full').glob('*/0')):
        result=read(out/'result.json');task=out.parent.name
        if result['status']=='validated_finished':
            completed[task]=hashlib.sha256((out/'result.json').read_bytes()).hexdigest();continue
        assert result['status'] in ['error','skipped_stalled']
        events=sorted(out.glob('events_*.jsonl'));session=None
        for eventfile in events:
            for line in eventfile.read_text().splitlines():
                try:e=json.loads(line)
                except ValueError:continue
                if e.get('type')=='thread.started':session=e['thread_id']
        state=read(out/'state.json');session=session or state.get('session');assert session,task
        segment=max(int(p.stem.split('_')[1]) for p in events)+1
        count=sum(read(p).get('response',{}).get('choices',[{}])[0].get('finish_reason')=='length' for p in (out/'api').glob('*.json'))
        assert count<3,(task,count)
        ledger=out/'oracle_queries.jsonl'
        plans.append((out,state,session,segment,count,hashlib.sha256(ledger.read_bytes()).hexdigest()))
    assert len(plans)==15 and len(completed)==8
    manifest={'time':time.time(),'mode':'resume same native session and ledger','completed_result_hashes':completed,'tasks':[]}
    for out,state,session,segment,count,digest in plans:
        dest=archive/out.parent.name;dest.mkdir()
        for name in ['result.json','state.json','error.json','transport_error.json','watchdog.json','config.json','initial_prompt.txt','top10_trajectory.json','oracle_queries.jsonl']:
            if (out/name).exists():shutil.copy2(out/name,dest/name)
        state.update(session=session,segment=segment,status='queued_recovery',recovery_pending=True)
        write(out/'state.json',state);write(out/'truncation_state.json',{'count':count,'historical':True})
        (out/'result.json').unlink()
        manifest['tasks'].append({'task':out.parent.name,'session':session,'next_segment':segment,'prior_truncations':count,'ledger_sha256':digest})
    write(archive/'manifest.json',manifest)
    print(json.dumps({'prepared':len(plans),'preserved_completed':len(completed),'tasks':[x['task'] for x in manifest['tasks']]}))
