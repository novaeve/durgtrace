"""Regression tests for user-requested continuation and truncated-output handling."""
import json,pathlib,tempfile,types,shutil
import pmo_common as c
import run_pmo as run

class Response:
    status_code=200
    def json(self):return {'choices':[{'finish_reason':'length','message':{'content':'C'*16384}}],'usage':{}}
    def close(self):pass
class Session:
    def __init__(self):self.n=0
    def post(self,*a,**kw):self.n+=1;return Response()

def test_truncations():
    with tempfile.TemporaryDirectory(dir=c.ROOT) as tmp:
        out=pathlib.Path(tmp);r=c.Relay(out);r.session=Session()
        for label in ['one','one','two','three']:
            try:r.complete([{'role':'user','content':'test'}],label)
            except c.LongTruncation:pass
            else:raise AssertionError('Truncated response escaped to candidate parser')
        assert r.session.n==3 and len(r.long_truncations)==3
        resumed=c.Relay(out);assert len(resumed.long_truncations)==3
        assert r.complete([{'role':'user','content':'test'}],'native_cap',cap=256)=='C'*16384
        assert len(r.long_truncations)==3

def test_no_progress_continues():
    original_root=run.ROOT;original_factory=run.make_oracle;original_method=run.METHODS['deepseek'];original_relay=run.Relay
    try:
        with tempfile.TemporaryDirectory(dir=c.ROOT) as tmp:
            root=pathlib.Path(tmp);run.ROOT=root
            for name in ['run_pmo.py','pmo_common.py','adapters.py','task_specs.py']:shutil.copy2(original_root/name,root/name)
            c.dump(root/'prepared/dependencies.json',{})
            # Simple distinct molecules with a fake cheap oracle; no real API calls.
            c.dump(root/'prepared/initial.json',{'0':['C'*i for i in range(1,101)]})
            out=root/'runs/full/deepseek/qed/0'
            c.dump(out/'state.json',{'episode':100,'no_progress':100})
            calls=[]
            run.make_oracle=lambda name:lambda sm:.5
            run.Relay=lambda out:types.SimpleNamespace(long_truncations=set(),usage=lambda:{})
            run.METHODS['deepseek']=lambda *args:calls.append(True) or {'test':'duplicate_only'}
            assert run.job('deepseek','qed',0,'full',1000)=='yielded'
            assert len(calls)==100
            state=json.loads((out/'state.json').read_text());assert state['episode']==200 and state['no_progress']==200
            assert not (out/'result.json').exists()
            # Three truncations are an explicit terminal skip, not a failed suite.
            run.Relay=lambda out:types.SimpleNamespace(long_truncations={'a','b','c'},usage=lambda:{})
            run.job('deepseek','qed',0,'full',1000)
            result=json.loads((out/'result.json').read_text())
            assert result['status']=='skipped_long_truncation' and result['oracle_calls']==100
    finally:
        run.ROOT=original_root;run.make_oracle=original_factory;run.METHODS['deepseek']=original_method;run.Relay=original_relay

if __name__=='__main__':
    assert run.SEEDS==[0] and len(run.TASKS)*len(run.METHODS)==92
    test_truncations();test_no_progress_continues()
    c.dump(c.ROOT/'prepared/policy_v2_validation.json',{'passed':True,'single_seed_jobs':92,'cached_truncation_counted_once':True,'native_256_cap_excluded':True,'no_progress_100_continues':True,'three_truncations_skip':True,'round_robin_yields_without_ending_search':True})
    print('Policy v2 regression checks passed')
