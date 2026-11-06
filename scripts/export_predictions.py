"""Extract final submissions from saved result.json files, without reading API traces."""
from pathlib import Path
import argparse,json
def field(row,path):
    for part in path.split('.'):
        if not isinstance(row,dict):return None
        row=row.get(part)
    return row
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_directory',type=Path);p.add_argument('--candidate-field',default='candidate');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=[];seen=set()
    for file in sorted(a.run_directory.rglob('result.json')):
        row=json.loads(file.read_text(encoding='utf-8'));id=row.get('id',row.get('case',{}).get('id'))
        if id is None:continue
        if id in seen:raise ValueError('Multiple results for '+id+'; choose one retained run directory')
        seen.add(id);rows.append({'id':id,'candidate':field(row,a.candidate_field),'status':row.get('status','complete')})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    print(json.dumps({'exported':len(rows),'output':str(a.output)}))
if __name__=='__main__':main()
