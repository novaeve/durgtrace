from pathlib import Path
import json
import subprocess
import time
import run
import score


def validate_runtime(stage):
    rows = []
    for path in sorted((run.ROOT / 'runs' / stage).glob('*/result.json')):
        case = json.loads(path.read_text())
        loaded = json.loads((run.ROOT / 'work' / stage / case['id'] / '.pi/loaded-runtime.json').read_text())
        assert loaded['provider'] == 'mol-edit-deepseek' and loaded['model'] == run.MODEL
        assert loaded['config'] == run.FLAGS
        tools = {tool['name']: tool['parameters'] for tool in loaded['tools']}
        assert all(name in tools for name in ('bash', 'write', 'edit', 'obs_recall', 'update_plan'))
        assert all('then_run' in tools[name]['properties'] for name in ('write', 'edit'))
        requests = 0
        for api in (path.parent / 'api').glob('*.json'):
            record = json.loads(api.read_text())
            actual = record['settings']
            assert actual['model'] == run.MODEL and actual['temperature'] == 0
            assert actual['enable_thinking'] is False and actual['reasoning_effort'] is None
            if record.get('response'):
                assert record['response']['model'] == run.MODEL
                requests += 1
        assert requests
        rows.append({'id': case['id'], 'status': case['status'], 'actual_requests': requests})
    assert rows
    run.dump(run.ROOT / 'preflight' / f'{stage}_runtime_validation.json', {'passed': True, 'rows': rows})


def main():
    evaluate, original = score.original_evaluator()
    work = run.ROOT / 'preflight/isolation'
    run.prepare_workspace(work)
    hidden = [str(run.ROOT / 'cases.json'), str(run.ROOT / 'original_cases.json'),
              '/data2/chenfuxin/chatdrug_generalization_20260920/prepared_full/cases.json',
              '/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env']
    code = 'import os,rdkit; paths=' + repr(hidden) + '; assert all(not os.path.exists(p) for p in paths); print(rdkit.__version__)'
    proc = subprocess.run(run.sandbox(work, 1) + ['python', '-c', code], text=True, capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert original.rdkit.__version__ in proc.stdout, proc.stdout
    model = subprocess.run(run.command(work, 1, models=True), text=True, capture_output=True, timeout=60)
    assert model.returncode == 0 and run.MODEL in model.stdout, model.stderr
    reps = [case for case in run.cases() if case['index'] == 0]
    assert len(reps) == 34
    for case in reps:
        previous = Path('/data2/chenfuxin/agentdrug_20260922/runs/full') / case['id'] / 'result.json'
        row = json.loads(previous.read_text())
        assert evaluate(case, row['candidate']) == row['score'], case['id']
        assert not evaluate(case, None)['success']
        assert not evaluate(case, case['smiles'])['success']
    smoke = {'id': 'native_tool_smoke', 'bench': 'SMOKE', 'bucket': 'smoke', 'instruction': ''}
    prompt = ('Use native bash to run Python, import rdkit, compute 17*19 and write 323 to probe.txt. '
              'Read it back. Use native write with then_run to create fused.txt containing 323 and validate '
              'it using cat. Use update_plan. Finish saying SMOKE_OK. Do not solve any molecule task.')
    result = run.execute(smoke, 'smoke', prompt_override=prompt)
    assert result['status'] == 'complete' and result['tool_calls'] >= 2, result
    assert (run.ROOT / 'work/smoke/native_tool_smoke/probe.txt').read_text().strip() == '323'
    assert (run.ROOT / 'work/smoke/native_tool_smoke/fused.txt').read_text().strip() == '323'
    validate_runtime('smoke')
    run.dump(run.ROOT / 'preflight/result.json', {'passed': True, 'original_scorer_checks': 34,
             'native_and_scorer_rdkit_version': original.rdkit.__version__,
             'case_metadata_hidden': True, 'native_tool_smoke': True, 'all_four_mechanisms': True,
             'time': time.time()})
    print('SOL_PI_ORIGINAL_PROTOCOL_PREFLIGHT_PASSED', flush=True)


if __name__ == '__main__':
    main()
