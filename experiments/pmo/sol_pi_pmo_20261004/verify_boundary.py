import tempfile
import time
from pathlib import Path
import run
from pmo_common import dump

with tempfile.TemporaryDirectory(dir=run.ROOT / 'preflight') as temp:
    out, work = Path(temp) / 'control', Path(temp) / 'work'
    out.mkdir(); work.mkdir()
    boundary = run.Boundary(out, work, 'qed', 7)
    boundary.oracle.evaluator = lambda smiles: 0.5
    first = boundary.call('score_molecules', {'smiles': ['CC', 'CC', 'INVALID']})
    assert first['used'] == 3
    assert first['results'][1]['status'] == 'duplicate'
    assert first['results'][2]['status'] == 'invalid'
    before = len(boundary.oracle.ledger().rows)
    result = boundary.call('python', {'code': 'from rdkit import Chem\nprint(Chem.MolToSmiles(Chem.MolFromSmiles("CO")))'})
    assert result['exit_code'] == 0 and 'CO' in result['output']
    assert len(boundary.oracle.ledger().rows) == before
    result = boundary.call('protocol_guard', {'name': 'write', 'input': {
        'path': '/workspace/cheat.py', 'content': 'from rdkit.Chem import QED\nprint(QED.qed(None))'}})
    assert result['reason']
    result = boundary.call('protocol_guard', {'name': 'read', 'input': {'path': str(run.BASELINE / 'full_summary.json')}})
    assert result['reason']
    (work / 'candidates.smi').write_text('CCO\nCCN\n')
    result = boundary.call('score_file', {'path': '/workspace/candidates.smi'})
    assert result['used'] == 5
    result = boundary.call('score_molecules', {'smiles': ['CCC', 'CCCC', 'CCCCC']})
    assert result['used'] == 7 and result['not_evaluated'] == 1
    assert len(boundary.oracle.ledger().rows) == 7
    report = dict(accepted=True, duplicate_invalid_charge='PASS', hard_cap='PASS',
        guarded_rdkit_python='PASS', python_does_not_charge_oracle='PASS',
        outside_result_read_denied='PASS', objective_reconstruction_denied='PASS',
        score_file_path_mapping='PASS', time=time.time())
    dump(run.ROOT / 'preflight/boundary_tests.json', report)
    print('BOUNDARY_TESTS_PASS')
