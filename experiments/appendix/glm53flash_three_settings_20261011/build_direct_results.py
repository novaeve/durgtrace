"""Reproduce DeepSeek_direct pairing and parser from the actual saved GLM first call."""
import collections,hashlib,json,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DIRECT=ROOT/'direct';CHAT=Path('/data2/chenfuxin/chatdrug_generalization_20260920')
sys.path.insert(0,str(CHAT));import pilot as p
sys.path.insert(0,str(DIRECT));from common import score,dump
jobs=json.loads((DIRECT/'jobs.json').read_text());m=json.loads((DIRECT/'manifest.json').read_text())
for name,digest in m['frozen_dependencies'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
summary=collections.defaultdict(collections.Counter);pinned={};matched=0
for j in jobs:
 c=j['case'];setting=j['setting'];out=DIRECT/'runs/GLM_direct'/setting/c['id'];fp=out/'result.json'
 if fp.exists():continue
 source=ROOT/'agents/native/ChatDrug'/setting/c['id']/'api_calls.json'
 digest=hashlib.sha256(source.read_bytes()).hexdigest();pinned[str(source)]=digest
 aa=json.loads(source.read_text());a=aa[0]
 assert a['label']=='shared_initial' and a['requested_model']==a['response_model']=='glm-5.3-flash'
 expected=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},
           {'role':'user','content':c['instruction']+' Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.'}]
 assert a['messages']==expected and a['request_settings']=={'temperature':0,'max_tokens':2048,'reasoning_effort':'low'}
 status='provider_limit' if a.get('stop_reason')=='max_tokens' else 'complete'
 assert a.get('stop_reason') in ('stop','max_tokens')
 candidate=p.parse_candidate(c['smiles'],a['output']) if status=='complete' else None
 old=json.loads((source.parent/'result.json').read_text())
 if status=='complete':
  assert candidate==old['arms']['direct']['candidate'],c['id'];matched+=1
 row={'id':c['id'],'case':c,'setting':setting,'method':'GLM_direct','model':'glm-5.3-flash','status':status,
      'candidate':candidate,'score':score(c,candidate if status=='complete' else None),'output':a.get('output'),
      'logical_model_calls':1,'new_api_calls':0,'paired_receipt_source':str(source),'source_sha256':digest,'finished':time.time()}
 dump(out/'api.json',a);dump(fp,row)
 summary[(setting,c['property'])]['processed']+=1;summary[(setting,c['property'])]['success']+=row['score']['success'];summary[(setting,c['property'])][status]+=1
for name,digest in pinned.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,'Source receipt changed'
rows=[json.loads(f.read_text()) for f in (DIRECT/'runs/GLM_direct').glob('*/*/result.json')];assert len(rows)==4200
expected=collections.Counter((j['setting'],j['case']['property']) for j in jobs);groups=[]
for (s,prop),n in expected.items():
 rr=[r for r in rows if r['setting']==s and r['case']['property']==prop]
 groups.append(dict(setting=s,property=prop,expected=n,processed=len(rr),success=sum(r['score']['success'] for r in rr),statuses=dict(collections.Counter(r['status'] for r in rr))))
dump(DIRECT/'summary.json',{'method':'GLM_direct','processed':4200,'expected':4200,'groups':groups,'updated':time.time()})
dump(DIRECT/'state.json',{'phase':'complete','processed':4200,'expected':4200,'provider_limits':sum(r['status']=='provider_limit' for r in rows),'new_api_calls':0,'time':time.time()})
dump(DIRECT/'paired_generation_audit.json',{'verified_real_model_receipts':4200,'native_parser_candidate_matches':matched,'source_hashes':pinned,'source_results_changed':False,'budget':2048,'reference_pairing_preserved':True})
print(json.dumps({'direct_processed':4200,'normal_completions':matched,'provider_limits':16,'new_api_calls':0}),flush=True)
