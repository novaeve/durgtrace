import pathlib,json,statistics,datetime
ROOT=pathlib.Path(__file__).resolve().parent
def stats(values):
 v=sorted(values)
 if not v:return {'n':0}
 return {'n':len(v),'mean':round(statistics.mean(v),3),'median':round(statistics.median(v),3),'p90':round(v[min(len(v)-1,int(.9*len(v)))],3)}
official={};bailian={}
for stage,dest in [('full',official),('single_bailian_full',bailian)]:
 for f in (ROOT/'runs'/stage).glob('*/result.json'):
  row=json.loads(f.read_text())
  if row['status']!='complete':continue
  calls=json.loads((f.parent/'api_calls.json').read_text());dest[row['id']]=(row,calls)
matched=[];clean=[];different=0
for key,(br,bc) in bailian.items():
 if key not in official:continue
 ar,ac=official[key]
 if len(ac)!=1 or not bc:continue
 if ac[0]['messages']!=bc[0]['messages']:different+=1;continue
 matched.append((ar,ac,br,bc))
 if any(c.get('stop_reason')=='max_tokens' or len(c['attempts'])!=1 or c['attempts'][0].get('status')!=200 for c in ac+bc):continue
 clean.append((ar,ac,br,bc))
def analyze(rows):
 return {
 'official_case_seconds_proxy':stats([a['seconds'] for a,ac,b,bc in rows]),
 'official_response_headers_seconds_NOT_total':stats([ac[0]['attempts'][0]['seconds'] for a,ac,b,bc in rows]),
 'bailian_generation_response_seconds':stats([bc[0]['attempts'][-1]['seconds'] for a,ac,b,bc in rows]),
 'bailian_selection_response_seconds':stats([bc[1]['attempts'][-1]['seconds'] for a,ac,b,bc in rows if len(bc)>1]),
 'bailian_case_seconds':stats([b['seconds'] for a,ac,b,bc in rows]),
 'official_generation_output_tokens':stats([ac[0].get('usage',{}).get('output_tokens',0) for a,ac,b,bc in rows]),
 'bailian_generation_output_tokens':stats([bc[0].get('usage',{}).get('output_tokens',0) for a,ac,b,bc in rows]),
 'bailian_selection_output_tokens':stats([bc[1].get('usage',{}).get('output_tokens',0) for a,ac,b,bc in rows if len(bc)>1]),
 'official_output_tokens_per_case_second_proxy':stats([ac[0].get('usage',{}).get('output_tokens',0)/a['seconds'] for a,ac,b,bc in rows if a['seconds']>0]),
 'bailian_output_tokens_per_response_second':stats([bc[0].get('usage',{}).get('output_tokens',0)/bc[0]['attempts'][-1]['seconds'] for a,ac,b,bc in rows if bc[0]['attempts'][-1]['seconds']>0]),
 'paired_generation_time_ratio_proxy':stats([bc[0]['attempts'][-1]['seconds']/a['seconds'] for a,ac,b,bc in rows if a['seconds']>0]),
 }
similar=[x for x in clean if .9<=x[3][0].get('usage',{}).get('output_tokens',0)/max(1,x[1][0].get('usage',{}).get('output_tokens',0))<=1.1]
out={'timestamp':datetime.datetime.now().isoformat(),'official_completed':len(official),'bailian_completed':len(bailian),'matched_messages':len(matched),'different_messages':different,'clean':analyze(clean),'similar_output_length_within_10pct':analyze(similar),'limitations':['Official streaming timer ends at response headers, not stream completion. Official case duration is used as a proxy including decomposition, PubChem lookup, reassembly, scoring, and local I/O.','Bailian non-streaming timer includes full response receipt.','Historical observational comparison, not simultaneous randomized provider benchmark.']}
(ROOT/'timing_comparison.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
