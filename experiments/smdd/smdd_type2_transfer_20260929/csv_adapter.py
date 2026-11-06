"""Format-only adapter; never infers or evaluates pharmacophore locations."""
import csv,io,math,re

TYPES={'Donor','Acceptor','Aromatic','Hydrophobic','Cation','Anion'}

def extract_csv(raw):
    # Format extraction only: use first explicitly delimited CSV, otherwise the
    # complete response. Never scan candidates or choose by task correctness.
    match=re.search(r'<csv>(.*?)</csv>',raw,re.S|re.I)
    if match:return match.group(1).strip()
    match=re.search(r'```(?:csv)?\s*\n(.*?)```',raw,re.S|re.I)
    return match.group(1).strip() if match else raw.strip()

def format_feedback(raw):
    rows=list(csv.reader(io.StringIO(extract_csv(raw))))
    problems=[]
    if len(rows)!=3:problems.append(f'Expected exactly 3 rows without a header; received {len(rows)}.')
    for i,row in enumerate(rows,1):
        if len(row)!=4:
            problems.append(f'Row {i}: expected four columns x,y,z,type.')
            continue
        try:
            if not all(math.isfinite(float(x)) for x in row[:3]):raise ValueError()
        except ValueError:problems.append(f'Row {i}: coordinates must be finite numbers.')
        if row[3].strip() not in TYPES:problems.append(f'Row {i}: type must be Donor, Acceptor, Aromatic, Hydrophobic, Cation, or Anion.')
    return not problems, ('CSV format is valid. Point locations and interaction types have not been evaluated for task correctness.' if not problems else 'CSV format is invalid. '+' '.join(problems))

if __name__=='__main__':
    assert format_feedback('0,0,0,Donor\n1,2,3,Acceptor\n4,5,6,Aromatic')[0]
    assert format_feedback('9999,9999,9999,Donor\n1,2,3,Acceptor\n4,5,6,Aromatic')[0]
    assert not format_feedback('nan,0,0,Donor\n1,2,3,Acceptor\n4,5,6,Aromatic')[0]
    assert not format_feedback('0,0,0,INVALID\n1,2,3,Acceptor\n4,5,6,Aromatic')[0]
    assert not format_feedback('0,0,0,Donor')[0]
    print('format-only tests passed')
