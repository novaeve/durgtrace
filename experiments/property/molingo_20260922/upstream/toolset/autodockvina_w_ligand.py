import requests
import os
from Bio.PDB import MMCIFParser, PDBIO, Select, PDBParser, NeighborSearch
import numpy as np
import subprocess
import shutil
from rdkit import Chem
from rdkit.Chem import AllChem
from tqdm import tqdm


# --- CONFIGURATION ---
MGLTOOLS_PATH = '/shared/nas2/thaotn2/anaconda3/envs/NP'
VINA_EXE = 'vina'
PY2_EXE = shutil.which('python2') or os.path.join(MGLTOOLS_PATH, 'bin', 'pythonsh')

def docked_pdbqt_to_pdb(pdbqt_path, output_pdb_path):
    """Converts Vina output to PDB to preserve docked coordinates."""
    with open(pdbqt_path, 'r') as f_in, open(output_pdb_path, 'w') as f_out:
        for line in f_in:
            if line.startswith("ENDMDL"): break 
            if line.startswith(("ATOM", "HETATM")):
                f_out.write(line[:66] + "\n")
    return output_pdb_path

def get_protein_data(pdb_file):
    parser = PDBParser(QUIET=True)
    struct = parser.get_structure('obj', pdb_file)
    atoms = [a for a in struct.get_atoms() if a.element.strip().upper() != 'H']
    coords = np.array([a.coord for a in atoms])
    return coords, atoms

def download_cif(filename, output_dir='./temp'):
    if not os.path.exists(output_dir): 
        os.makedirs(output_dir, exist_ok=True)

    url = f"https://files.rcsb.org/download/{filename}"
    response = requests.get(url)
    response.raise_for_status() 
    save_path = os.path.join(output_dir, 'protein.cif')
    with open(save_path, "wb") as f:
        f.write(response.content)
    return save_path

class ProteinSelect(Select):
    def __init__(self, ligand_id=None):
        self.ligand_id = ligand_id
    
    def accept_residue(self, residue):
        resname = residue.get_resname().strip()
        if resname == self.ligand_id or resname in ['HOH', 'DOD']:
            return 0
        return 1

def prep_cif_for_docking(cif_input, ligand_id, padding=12, save_dir='./temp'):
    parser = MMCIFParser(QUIET=True)
    structure = parser.get_structure('complex', cif_input)
    model = structure[0]

    ligand_coords = []
    for chain in model:
        for residue in chain:
            if residue.get_resname().strip() == ligand_id:
                for atom in residue:
                    ligand_coords.append(atom.get_coord())
                    
    if not ligand_coords:
        raise ValueError(f"Ligand {ligand_id} not found in the file.")
    
    ligand_coords = np.array(ligand_coords)
    center = np.mean(ligand_coords, axis=0)
    size = (np.max(ligand_coords, axis=0) - np.min(ligand_coords, axis=0)) + padding

    receptor_pdb_name = os.path.basename(cif_input.replace('.cif', '_receptor.pdb'))
    receptor_pdb_path = os.path.join(save_dir, receptor_pdb_name)
    
    io = PDBIO()
    io.set_structure(structure)
    io.save(receptor_pdb_path, select=ProteinSelect(ligand_id))
    return receptor_pdb_path, center, size

# ---------------- PDB → PDBQT (Fixed Path Handling) ----------------
def convert_to_pdbqt(input_pdb_path, is_receptor=True):
    save_dir = os.path.dirname(input_pdb_path)
    input_file_name = os.path.basename(input_pdb_path)
    output_file_name = input_file_name.replace('.pdb', '.pdbqt')
    
    script = 'prepare_receptor4.py' if is_receptor else 'prepare_ligand4.py'
    script_path = os.path.join(MGLTOOLS_PATH, 'MGLToolsPckgs', 'AutoDockTools', 'Utilities24', script)

    cmd = [PY2_EXE, script_path, '-o', output_file_name]
    if is_receptor:
        cmd += ['-r', input_file_name]
    else:
        cmd += ['-l', input_file_name, '-A', 'hydrogens']

    # Execute inside the temp directory
    subprocess.run(cmd, check=True, cwd=os.path.abspath(save_dir), capture_output=True)
    return os.path.join(save_dir, output_file_name)


def identify_accurate_growth(receptor_pdb, docked_pdb, contact_threshold=7.0, max_hotspots=5):
    parser = PDBParser(QUIET=True)
    receptor_struct = parser.get_structure('receptor', receptor_pdb)
    ligand_struct = parser.get_structure('ligand', docked_pdb)
    
    # Setup NeighborSearch for residue lookup
    receptor_atoms = [a for a in receptor_struct.get_atoms() if a.element.strip().upper() != 'H']
    ns = NeighborSearch(receptor_atoms)
    
    ligand_atoms = [a for a in ligand_struct.get_atoms() if a.element.strip().upper() != 'H']
    ligand_coords = np.array([a.coord for a in ligand_atoms])
    receptor_coords = np.array([a.coord for a in receptor_atoms])
    
    hotspots = []

    for i, l_atom in enumerate(ligand_atoms):
        l_coord = l_atom.coord
        # Get both pieces of info
        l_index = i
        l_type = l_atom.element.strip().upper()
        
        # 1. Find Nearby Residues
        nearby_res_objs = ns.search(l_coord, contact_threshold, level='R')
        nearby_residues = [f"{r.get_resname()}{r.get_id()[1]}" for r in nearby_res_objs]
        
        # 2. Estimate Available Volume
        grid_size = 0.5  
        box_edge = 5.0
        grid_points = np.mgrid[
            l_coord[0]-box_edge/2 : l_coord[0]+box_edge/2 : grid_size,
            l_coord[1]-box_edge/2 : l_coord[1]+box_edge/2 : grid_size,
            l_coord[2]-box_edge/2 : l_coord[2]+box_edge/2 : grid_size
        ].reshape(3, -1).T
        
        if len(grid_points) > 0:
            prot_dists = np.min(np.linalg.norm(grid_points[:, None] - receptor_coords, axis=2), axis=1)
            lig_dists = np.min(np.linalg.norm(grid_points[:, None] - ligand_coords, axis=2), axis=1)
            
            # Count "Empty" points (standard VdW buffers)
            valid_points = np.sum((prot_dists > 2.2) & (lig_dists > 1.2))
            volume = valid_points * (grid_size ** 3)
        else:
            volume = 0.0

        hotspots.append({
            "ligand_atom_index": l_index,
            "ligand_atom_type": l_type,
            "volume_A3": volume,
            "nearby_residues": list(set(nearby_residues))
        })

    # Sort by volume (largest growing space first)
    hotspots = sorted(hotspots, key=lambda x: x['volume_A3'], reverse=True)
    
    return hotspots[:max_hotspots]

# ---------------- SMILES → Ligand PDBQT (Fixed Path Handling) ----------------
def prepare_ligand_pdb(smiles, ligand_name='ligand', save_dir='./temp'):
    os.makedirs(save_dir, exist_ok=True)
    pdb_file_name = f"{ligand_name}.pdb"
    pdbqt_file_name = f"{ligand_name}.pdbqt"
    
    pdb_full_path = os.path.join(save_dir, pdb_file_name)
    pdbqt_full_path = os.path.join(save_dir, pdbqt_file_name)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
        raise RuntimeError("RDKit failed to generate 3D coordinates")
    AllChem.MMFFOptimizeMolecule(mol)

    pdb_block = Chem.MolToPDBBlock(mol)
    with open(pdb_full_path, 'w') as f:
        for line in pdb_block.splitlines():
            if line.startswith("ATOM  "):
                f.write("HETATM" + line[6:] + "\n")
            else:
                f.write(line + "\n")

    script_path = os.path.join(MGLTOOLS_PATH, 'MGLToolsPckgs', 'AutoDockTools', 'Utilities24', 'prepare_ligand4.py')
    
    cmd = [PY2_EXE, script_path, '-l', pdb_file_name, '-o', pdbqt_file_name, '-A', 'hydrogens']
    
    # Run in the local directory to avoid path assertion errors
    subprocess.run(cmd, check=True, cwd=os.path.abspath(save_dir))

    return pdb_full_path, pdbqt_full_path

# ---------------- Run Vina ----------------
def run_vina(receptor_pdbqt, ligand_pdbqt, center, size, ligand_name='ligand', save_dir='./temp'):
    out_pdbqt = os.path.join(save_dir, f"docked_{ligand_name}.pdbqt")
    log_file = os.path.join(save_dir, f"log_{ligand_name}.txt")

    cmd = [
        VINA_EXE,
        '--receptor', receptor_pdbqt,
        '--ligand', ligand_pdbqt,
        '--center_x', str(center[0]),
        '--center_y', str(center[1]),
        '--center_z', str(center[2]),
        '--size_x', str(size[0]),
        '--size_y', str(size[1]),
        '--size_z', str(size[2]),
        '--out', out_pdbqt,
        '--log', log_file
    ]

    subprocess.run(cmd, check=True, capture_output=True)

    score = None
    with open(log_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and line[0].isdigit():
                parts = line.split()
                if parts[0] == "1":
                    score = float(parts[1])
                    break
    return score, out_pdbqt

# ---------------- Full Pipeline ----------------
def autodockvina_w_ligand(cif_id, ligand_id, smiles, save_dir='./temp', sbdd=True, contact_threshold=7.0, max_hotspots=5):
    os.makedirs(save_dir, exist_ok=True)
    cif_file = f'{cif_id}.cif' if not cif_id.endswith('.cif') else cif_id

    # 1. Download and Prep
    cif_path = download_cif(cif_file, save_dir)
    receptor_pdb, center, size = prep_cif_for_docking(cif_path, ligand_id, save_dir=save_dir)
    receptor_pdbqt = convert_to_pdbqt(receptor_pdb, is_receptor=True)
    if isinstance(smiles, str):
        _, ligand_pdbqt = prepare_ligand_pdb(smiles, 'ligand', save_dir=save_dir)

        # 2. Docking
        score, out_pdbqt = run_vina(receptor_pdbqt, ligand_pdbqt, center, size, save_dir=save_dir)
        
        # 3. Growth Analysis (The NEW part)
        # Convert docked PDBQT to PDB to keep the new coordinates
        if sbdd:
            docked_pdb = os.path.join(save_dir, 'docked_aligned.pdb')
            docked_pdbqt_to_pdb(out_pdbqt, docked_pdb)
            growth_analysis = identify_accurate_growth(receptor_pdb, docked_pdb, contact_threshold=contact_threshold, max_hotspots=max_hotspots)
            return {
                "docking_score": score,
                "growth_hotspots": growth_analysis
            }
        else:
            return score
        
    if isinstance(smiles, list):
        SCORE = []
        for sm in tqdm(smiles, desc='Docking'):
            try:
                _, ligand_pdbqt = prepare_ligand_pdb(sm, 'ligand', save_dir=save_dir)
                score, out_pdbqt = run_vina(receptor_pdbqt, ligand_pdbqt, center, size, save_dir=save_dir)
                SCORE.append([sm, score])
            except:
                pass
        return SCORE

    
if __name__ == "__main__":
    # cif_input = '8HFF'
    # ligand_ref = 'LNR'
    cif_input = '3K6P'
    ligand_ref = '5FB'
    for test_smiles in ['O=C(N/N=C/C1=CC=C2C=CC=CC2=C1)C3=CC=C(O)C=C3', 'O=C(N/N=C/c1ccccc1)c1ccc(F)cc1', 'O=C(N/N=C/c1ccccc1)c1ccc(I)cc1', 'CON=Cc1ccc(C(=O)N/N=C/c2ccccc2)cc1', 'COc1ccc(/C=N/NC(=O)c2ccc(O)cc2)cc1', 'O=C(N/N=C/c1ccc(F)cc1)c1cccc(O)c1', 'O=C(N/N=C/c1ccc(F)cc1)c1ccc(O)c(F)c1', 'O=C(N/N=C/c1ccccc1)c1ccc(O)c(F)c1']:
        final_score = autodockvina_w_ligand(cif_input, ligand_ref, test_smiles)
        print(f"{cif_input} {test_smiles}: {final_score}")


