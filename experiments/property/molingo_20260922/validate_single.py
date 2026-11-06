import single_runner as s
for response in ['{"candidate_id": 2}','```json\n{"candidate_id": 2}\n```']:
 assert s.parse_selection(response,3)==1
for response in ['{"candidate_id": [1,2]}','{"candidate_id": 0}','{"candidate_id": 4}','{"candidate_id": true}','{"candidate_id": 1, "other": 2}','1 or 2']:
 try:s.parse_selection(response,3)
 except ValueError:pass
 else:raise AssertionError(response)
case={'instruction':'Increase QED','smiles':'CC'}
seen=[]
def complete(prompt,label):
 seen.append(prompt);return '{"candidate_id": 2}'
assert s.submit_one(case,['CC','CCC','CCCC'],complete)==('CCC',1,None)
assert len(seen)==1 and 'candidate_id' in seen[0]
assert s.submit_one(case,['CC'],complete)==('CC',0,None)
assert s.submit_one(case,[],complete)==(None,None,'NO_CANDIDATES')
assert len(seen)==1
print('PASS: strict single selection, no first/oracle fallback, singleton, empty output')
