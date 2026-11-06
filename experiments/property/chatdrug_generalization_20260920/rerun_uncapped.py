"""User-requested rerun of exactly five truncated cases; frozen original stays intact."""
import inspect,json,pathlib,sys,datetime,fcntl
import full_experiment as f
p=f.p
f.install()
source=inspect.getsource(p.Relay)
assert "'max_tokens':max_tokens," in source
# Preserve endpoint, messages, streaming, temperature, parsing and retry behavior.
source=source.replace("'max_tokens':max_tokens,",'',1)
source=source.replace("'max_tokens':max_tokens","'max_tokens':None,'output_limit_policy':'omitted; provider default'")
ns=dict(p.__dict__);exec(source,ns);p.Relay=ns['Relay']
OUT=p.ROOT/'runs/deepseek_uncapped5'
OUT.mkdir(parents=True,exist_ok=True)
if '--probe' in sys.argv:
 relay=p.Relay(OUT/'probe.json')
 try:
  text=relay.complete([{'role':'user','content':'Reply with exactly OK.'}],'probe_omitted_max_tokens')
  print(json.dumps({'probe':'passed','output':text,'settings':relay.calls[-1]['request_settings']}))
 except p.RelayError as e:print(json.dumps({'probe':'failed','error':str(e)}));raise SystemExit(2)
 raise SystemExit(0)
lock=(OUT/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
ids=['source_104_strict_176','source_104_loose_176','s2_QED_228198','s2_QED_8226','s2_QED_105651']
cases={c['id']:c for c in json.loads((f.PREP/'cases.json').read_text())}
for cid in ids:
 original=json.loads((f.OUT/cid/'result.json').read_text())
 assert original['status']=='error' and original['error']=='OUTPUT_TRUNCATED'
p.dump(OUT/'run_config.json',{'ids':ids,'change':'Omit max_tokens from Anthropic-compatible request; provider default applies, not infinite output.','original_results':'runs/deepseek_full unchanged','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runner_sha256':p.sha(__file__),'base_code_hashes':{n:p.sha(p.ROOT/n) for n in ('full_experiment.py','full_case.py','pilot.py','deepseek_check.py')},'scope':'Entire three-arm case rerun once, first output shared; only five user-selected truncation cases replaced in amended analysis.'})
db=p.pd.read_csv(f.PREP/'retrieval.csv')
for cid in ids:p.run_case(cases[cid],db,OUT)
rows=[]
for path in f.OUT.glob('*/result.json'):
 replacement=OUT/path.parent.name/'result.json'
 rows.append(json.loads((replacement if replacement.exists() else path).read_text()))
groups={};errors=[]
for r in rows:
 c=r['case'];key='ChatDrug' if c['benchmark']=='ChatDrug' else c['property']
 g=groups.setdefault(key,{'complete':0,'errors':0,'success':dict.fromkeys(['direct','chatdrug','independent3'],0)})
 if r['status']!='complete':g['errors']+=1;errors.append({'id':r['id'],'error':r.get('error')});continue
 g['complete']+=1
 for arm in g['success']:g['success'][arm]+=int(r['arms'][arm]['success'])
p.dump(OUT/'amended_summary.json',{'groups':groups,'errors':errors,'total':len(rows),'replaced_ids':ids,'note':'Amended mixed output-limit run; untouched cases retain original 2048 cap. Original summary retained.'})
print(json.dumps({'groups':groups,'errors':errors}),flush=True)
raise SystemExit(2 if errors else 0)
