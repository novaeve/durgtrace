from pathlib import Path
import json
import os
import subprocess
import run


def validate_runtime(stage):
    reports = []
    for result in sorted((run.ROOT / 'runs' / stage).glob('*/result.json')):
        row = json.loads(result.read_text())
        loaded = json.loads((run.ROOT / 'work' / stage / row['id'] / '.pi/loaded-runtime.json').read_text())
        assert loaded['provider'] == 'fourbench-deepseek' and loaded['model'] == run.MODEL
        assert loaded['config'] == run.FLAGS
        tools = {tool['name']: tool for tool in loaded['tools']}
        assert all(name in tools for name in ('bash', 'read', 'edit', 'write', 'obs_recall', 'update_plan'))
        assert all('then_run' in tools[name]['parameters']['properties'] for name in ('write', 'edit'))
        api = [json.loads(p.read_text()) for p in (result.parent / 'api').glob('*.json')]
        responses = 0
        for record in api:
            settings = record['settings']
            assert settings['temperature'] == 0 and settings['enable_thinking'] is False
            assert settings['reasoning_effort'] is None and settings['max_tokens'] is None
            assert settings['model'] == run.MODEL
            if record.get('response'):
                assert record['response']['model'] == run.MODEL
                responses += 1
        assert responses > 0
        reports.append({'id': row['id'], 'status': row['status'], 'actual_model_requests': len(api),
                        'native_fusion_tools': True, 'all_four_mechanisms': True})
    assert reports
    report = {'accepted': True, 'stage': stage, 'cases': reports}
    run.dump(run.ROOT / 'preflight' / f'{stage}_runtime_validation.json', report)
    return report


def main():
    manifest = json.loads((run.ROOT / 'manifest.json').read_text())
    for path, digest in {**manifest['baseline_files'], **manifest['frozen_inputs']}.items():
        assert run.sha(Path(path)) == digest, path
    work = run.ROOT / 'preflight/isolation'
    run.prepare_workspace(work)
    forbidden = [str(run.LANG / 'data/answers.json'), str(run.S2 / 'benchmark.py'),
                 str(run.BASELINE / 'cases.json'), str(run.BASELINE / 'runs'),
                 '/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env']
    code = 'import os,rdkit; paths=' + repr(forbidden) + '; assert all(not os.path.exists(p) for p in paths); print("isolation_rdkit_ok")'
    checked = subprocess.run(run.sandbox(work, 1) + ['python', '-c', code], text=True,
                             capture_output=True, timeout=60)
    assert checked.returncode == 0, checked.stderr
    assert 'isolation_rdkit_ok' in checked.stdout
    listed = subprocess.run(run.command(work, 1, models=True), text=True, capture_output=True, timeout=60)
    assert listed.returncode == 0 and run.MODEL in listed.stdout, listed.stderr
    smoke = {'id': 'tool_smoke', 'bench': 'SMOKE', 'bucket': 'smoke', 'prompt': ''}
    prompt = ('Work only in /workspace. Use native bash to run Python, import rdkit, compute 17*19, '
              'and write 323 to probe.txt. Read it back. Use native write to create fused.txt containing 323 '
              'with then_run to validate it using cat. Use update_plan for this test. Finish saying SMOKE_OK. '
              'Do not solve any benchmark molecule task.')
    result = run.execute(smoke, 'smoke', prompt_override=prompt)
    assert result['status'] == 'complete', result['status']
    probe = run.ROOT / 'work/smoke/tool_smoke/probe.txt'
    assert probe.read_text().strip() == '323'
    assert result['tool_calls'] >= 2
    validate_runtime('smoke')
    run.dump(run.ROOT / 'preflight/result.json', {'accepted': True, 'rdkit': True,
             'hidden_files_unmounted': True, 'model_loading': True, 'native_tool_smoke': True})
    print('SOL_PI_FOURBENCH_PREFLIGHT_PASSED', flush=True)


if __name__ == '__main__':
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    main()
