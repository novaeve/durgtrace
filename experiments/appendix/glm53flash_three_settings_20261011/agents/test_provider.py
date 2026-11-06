"""Offline regression: immutable transcript, per-agent caps, prefix replay and truncation semantics."""
import copy,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/data2/chenfuxin/chatdrug_generalization_20260920');sys.path.insert(0,str(ROOT))
import provider
class Response:
    status_code=200
    def __init__(self,body):self.body=body
    def close(self):pass
    def json(self):
        return {'model':provider.MODEL,'choices':[{'message':{'content':'CCO'},'finish_reason':self.body.get('finish','stop')}],
                'usage':{'prompt_tokens':20,'completion_tokens':3,'completion_tokens_details':{'reasoning_tokens':0}}}
class Session:
    def __init__(self):self.posts=[]
    def close(self):pass
    def post(self,url,**kwargs):
        self.posts.append(copy.deepcopy(kwargs['json']));return Response(kwargs['json'])
fake={'base':'https://tok.fan/v1','key':'OFFLINE_SENTINEL_NEVER_LOG'}
folder=ROOT/'preflight/provider_test';folder.mkdir(parents=True,exist_ok=True)
with patch.object(provider,'config',return_value=fake),patch.object(provider.requests,'Session',Session):
    path=folder/'immutable.json'
    if path.exists():path.unlink()
    relay=provider.Relay(path);messages=[{'role':'user','content':'initial molecular request'}]
    assert relay.complete(messages,'initial')=='CCO'
    assert relay.session.posts[-1]['max_completion_tokens']==2048
    messages.append({'role':'assistant','content':'CCO'})
    messages.append({'role':'user','content':'feedback'})
    assert relay.complete(messages,'feedback',max_tokens=256)=='CCO'
    assert relay.session.posts[-1]['max_completion_tokens']==256
    assert len(relay.calls[0]['messages'])==1
    for body in relay.session.posts:
        assert body['model']=='glm-5.3-flash' and body['reasoning_effort']=='low' and body['temperature']==0
        assert 'enable_thinking' not in body
    assert fake['key'] not in path.read_text()
    replay=provider.Relay(path)
    assert replay.complete([{'role':'user','content':'initial molecular request'}],'initial')=='CCO'
    assert replay.complete(messages,'feedback',max_tokens=256)=='CCO'
    assert not replay.session.posts
    trunc=folder/'truncated.json'
    if trunc.exists():trunc.unlink()
    class LengthSession(Session):
        def post(self,url,**kwargs):
            body=copy.deepcopy(kwargs['json']);body['finish']='length';self.posts.append(body);return Response(body)
    with patch.object(provider.requests,'Session',LengthSession):
        relay=provider.Relay(trunc)
        try:relay.complete([{'role':'user','content':'long output'}],'length',max_tokens=256)
        except provider.RelayError as exc:assert str(exc)=='OUTPUT_TRUNCATED'
        else:raise AssertionError('Truncation must retain native signal')
        assert relay.calls[-1]['output']=='CCO'
        cached=provider.Relay(trunc)
        try:cached.complete([{'role':'user','content':'long output'}],'length',max_tokens=256)
        except provider.RelayError as exc:assert str(exc)=='OUTPUT_TRUNCATED'
        else:raise AssertionError('Replay must preserve truncation')
        assert not cached.session.posts
print('PROVIDER_NATIVE_COMPATIBILITY_PASSED')
