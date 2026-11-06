"""Produce an agent-public input directory; never copy witness/evaluation data."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import yaml
from Bio.SeqUtils import seq1
from rdkit import Chem

def prepare(task_dir, output):
    task_dir, output = Path(task_dir), Path(output)
    task = yaml.safe_load((task_dir/'task.yaml').read_text())
    output.mkdir(parents=True, exist_ok=False)
    files = task['input_files']
    if not {'complex.pdb','reference.sdf'} <= set(files):
        raise ValueError('Missing Type4 public inputs')
    if any(Path(x).name != x or 'witness' in x.lower() for x in files):
        raise ValueError('Unexpected public input path')
    for f in files:
        shutil.copy2(task_dir/f, output/f)
    # The agent receives the description and explicitly public structural fields only.
    public = {k:task[k] for k in ('id','description','target_ligand','pocket_residues')}
    (output/'public_task.json').write_text(json.dumps(public, indent=2))
    protein, ligand, residues = [], [], {}
    target = task['target_ligand']
    for line in (output/'complex.pdb').read_text().splitlines():
        if line.startswith('ATOM  '):
            protein.append(line)
            key=(line[21],int(line[22:26]),line[26])
            residues.setdefault(key,line[17:20].strip())
        elif line.startswith('HETATM') and line[21] == target['chain'] and int(line[22:26]) == target['residue_number'] and line[17:20].strip() == target['resname']:
            ligand.append([float(line[30:38]),float(line[38:46]),float(line[46:54])])
    if not protein or not ligand:
        raise ValueError('Could not locate protein and target ligand in public complex')
    center = [sum(p[i] for p in ligand)/len(ligand) for i in range(3)]
    (output/'protein.pdb').write_text('\n'.join(protein)+'\nEND\n')
    sequences={}
    indices={}
    for (chain,num,ins),name in residues.items():
        sequences[chain]=sequences.get(chain,'')+seq1(name, custom_map={'MSE':'M'})
        indices.setdefault(chain,[]).append((num,ins))
    # These co-folded inputs should use contiguous residue numbers matching public contacts.
    for chain,positions in indices.items():
        if positions != [(i,' ') for i in range(1,len(positions)+1)]:
            raise ValueError('Requires explicit SEQRES mapping: '+chain)
    mol=next(iter(Chem.SDMolSupplier(str(output/'reference.sdf'))))
    if mol is None:
        raise ValueError('Invalid reference ligand')
    derived={'center':center,'center_source':'target ligand in public complex.pdb',
             'reference_smiles':Chem.MolToSmiles(mol),
             'protein_sequences':[{'id':k,'sequence':v} for k,v in sequences.items()],
             'pocket_residues':task['pocket_residues']}
    (output/'derived.json').write_text(json.dumps(derived,indent=2))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output/'input_manifest.json').write_text(json.dumps({'task':task['id'],'source_input_files':files,'files':hashes},indent=2))
    return derived

if __name__=='__main__':
    print(json.dumps(prepare(sys.argv[1],sys.argv[2]),indent=2))
