from pathlib import Path
import hashlib,json,subprocess
from run import ROOT,BASE,CODEX,MOL,sandbox
from runtime import dump,isolated
rows={}
for method in ['molclaw','codex']:
    path=ROOT/'smoke'/method/'smdd_003_1JVP_1'
    result=json.loads((path/'result.json').read_text());assert result['status']=='complete',result
    traces=[json.loads(p.read_text()) for p in sorted((path/'api').glob('*.json'))]
    assert traces and all(t.get('response') for t in traces)
    for t in traces:
        r=t['request'];assert r['model']=='deepseek-v4.1-flash' and r['enable_thinking'] is True and r['reasoning_effort']=='high' and r['temperature']==1 and 'max_tokens' not in r
        assert t['response']['model']=='deepseek-v4.1-flash'
    rows[method]={'result':result,'verified_calls':len(traces),'reasoning_chars':sum(len(t['response']['choices'][0]['message'].get('reasoning_content') or '') for t in traces)}
    assert rows[method]['reasoning_chars']>0
    code="import os,socket; from pathlib import Path; assert not Path('/data2/chenfuxin/smdd_type3_transfer_20260930/tasks').exists(); assert not Path('/data2/chenfuxin/molingo_20260922/private').exists(); assert not os.environ.get('BAILIAN_API_KEY'); print('ISOLATED_OK')"
    text,rc=isolated(['python','-c',code],path/'workspace',30);assert rc==0 and 'ISOLATED_OK' in text
    p=subprocess.run(sandbox(path/'workspace',1)+['/usr/bin/test','!','-e',str(BASE/'tasks')]);assert p.returncode==0
dump(ROOT/'verification.json',rows)
manifest={'methods':['molclaw','codex'],'tasks':52,'model':'deepseek-v4.1-flash','enable_thinking':True,'reasoning_effort':'high','temperature':1,'max_calls':100,'cumulative_token_budget':10000000,'per_call_output_cap':None,'boltz_budget':8,'admet_budget':15,'seed':42,'official_commit':'359ef1d7c042b85fc1c544662b4fd6fb381f346f','source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')},'codex_sha256':hashlib.sha256(CODEX.read_bytes()).hexdigest(),'codex_version':subprocess.check_output([str(CODEX),'--version'],text=True).strip(),'molclaw_cli_version':subprocess.check_output([str(MOL/'runtime/node_modules/.bin/claude'),'--version'],text=True).strip(),'protocol':'实验协议.md','preserve_existing_three_groups':True}
dump(ROOT/'manifest.json',manifest)
print(json.dumps({'verified':True,'calls':{m:x['verified_calls'] for m,x in rows.items()},'reasoning_nonempty':True,'isolation_checked':True}))
