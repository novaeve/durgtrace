import sys,json,tempfile
from pathlib import Path
INSTALL=Path('/data2/chenfuxin/agent_reproduction_20260928')
sys.path.insert(0,str(INSTALL))
sys.path.insert(0,str(INSTALL/'Pocket2Mol'))
from prepare_type4 import prepare
from sample_for_pdb import pdb_to_pocket_data
ROOT=Path('/data2/chenfuxin/smdd_type3_transfer_20260930/tasks')
results=[]
with tempfile.TemporaryDirectory(prefix='type3_pocket_audit_') as tmp:
    for task in sorted(ROOT.glob('smdd_003*')):
        row={'task':task.name}
        try:
            out=Path(tmp)/task.name
            derived=prepare(task,out)
            data=pdb_to_pocket_data(str(out/'protein.pdb'),derived['center'],23.0)
            row.update(status='ok',pocket_atoms=int(data.protein_pos.shape[0]),
                       center=derived['center'],protein_chains=len(derived['protein_sequences']))
        except Exception as e:row.update(status='error',error=repr(e))
        results.append(row)
report={'total':len(results),'ok':sum(r['status']=='ok' for r in results),
        'results':results,'test':'public inputs + existing prepare + original Pocket2Mol pdb_to_pocket_data; no generation or oracle calls'}
(INSTALL/'audit_type3_pocket_result.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'total':report['total'],'ok':report['ok'],
                  'errors':[r for r in results if r['status']!='ok'],
                  'pocket_atoms_range':[min(r['pocket_atoms'] for r in results if r['status']=='ok'),max(r['pocket_atoms'] for r in results if r['status']=='ok')]}))
