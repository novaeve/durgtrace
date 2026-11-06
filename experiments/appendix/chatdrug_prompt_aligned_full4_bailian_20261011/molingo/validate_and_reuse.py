
import collections,json,hashlib,sys
from pathlib import Path
from common import score,dump,ROOT
method=json.loads((ROOT/'manifest.json').read_text())['method']
reference=Path('/data2/chenfuxin/chatdrug_prompt_aligned_bailian_20261006')
cases=json.loads((ROOT/'cases.json').read_text());byid={c['id']:c for c in cases}
checks=[];buckets=set()
for f in sorted((reference/'runs').rglob('result.json')):
    row=json.loads(f.read_text());c=row.get('case')
    if c is None or c.get('benchmark')!='ChatDrug':continue
    key=(row.get('method'),c['task'],c['constraint'])
    if key in buckets:continue
    buckets.add(key)
    candidate=row.get('candidate');oldscore=row.get('score_direction_only',{})
    if candidate is None and not oldscore:continue
    fresh=score(c,candidate if row.get('status')=='complete' else None)
    assert fresh['success']==oldscore['success'],(str(f),fresh,oldscore)
    checks.append(str(f))
    if len(checks)>=84:break
assert len(checks)>=28,('too few baseline validation rows',len(checks))
reuse=[]
old=Path('/data2/chenfuxin/molecule_s2_prompt_eval_20261007')
for path in sorted((old/'runs'/method).glob('*/result.json')):
    row=json.loads(path.read_text());c=byid.get(row['id'])
    if not c or row['case']['instruction']!=c['instruction']:continue
    assert row['status']=='complete'
    assert row['case']['smiles']==c['smiles'] and row['case']['objectives']==c['objectives']
    native=Path(row['native_result']);nr=json.loads(native.read_text())
    assert nr['candidate']==row['candidate']
    if method=='MolClaw':
        assert not nr.get('runtime_is_error')
        assert (native.parent/'prompt.txt').exists()
    else:
        assert nr['evaluation_calls']==1
    row['original_score']=row['score'];row.update(case=c,reused_from=str(path),reuse_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    row['score']=score(c,row.get('candidate'))
    dump(ROOT/'runs'/c['id']/'result.json',row)
    reuse.append(dict(id=c['id'],source=str(path),source_sha256=row['reuse_sha256']))
assert len(reuse)==320,len(reuse)
dump(ROOT/'validation.json',dict(passed=True,baseline_score_checks=len(checks),reused=len(reuse),denominator=5600,exact_case_hash=hashlib.sha256((ROOT/'cases.json').read_bytes()).hexdigest()))
dump(ROOT/'reuse_audit.json',dict(method=method,records=reuse,criteria='Exact input molecule, task instruction and native baseline code/config; no benchmark feedback during generation; all matched cases including failures reused'))
print(json.dumps(dict(method=method,validated=True,reused=len(reuse),pending=5600-len(reuse))))
