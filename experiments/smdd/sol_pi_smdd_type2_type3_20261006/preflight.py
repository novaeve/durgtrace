from pathlib import Path
import json
import subprocess
import time
import run
import runtime
from runtime import dump, Executor
from agent_harness.config import AgentConfig


def check(kind):
    cases = json.loads((run.ROOT / kind / 'public_cases.json').read_text())
    case = cases[0]
    work = run.ROOT / kind / 'preflight/models'
    run.prepare_workspace(work)
    proc = subprocess.run(run.command(kind, work, 1, models=True), text=True,
                          capture_output=True, timeout=60)
    assert proc.returncode == 0 and run.MODEL in proc.stdout, proc.stderr
    hidden = [str(run.ROOT / kind / 'tasks'), str(run.ROOT / 'source'),
              '/data2/chenfuxin/molingo_20260922/private', '/eval/code']
    for path in hidden:
        assert subprocess.run(run.sandbox(kind, work, 1) + ['/usr/bin/test', '!', '-e', path]).returncode == 0
    text, code = runtime.isolated(['python', '-c', 'import rdkit,numpy,scipy,Bio; print("scientific_environment_ok")'], work)
    assert code == 0 and 'scientific_environment_ok' in text, text[-500:]
    executor = Executor(str(work), AgentConfig(admet_budget=0, boltz_budget=0))
    for name in ('predict_admet', 'predict_boltz'):
        assert executor.dispatch(name, {})[1].get('budget_exceeded')
    prompt = ('This is a transport and tool smoke test, not a benchmark attempt. '
              'Use the SMDD python tool to import rdkit and compute 17*19, write 323 into probe.txt, '
              'and read it back. Use native write to create fused.txt containing 323 with then_run '
              'to run wc -c fused.txt. Use update_plan to track this test. '
              'Finally call the SMDD submit tool with file_path="probe.txt". Do not solve the real molecular task.')
    result = run.job(kind, case, stage='smoke', prompt_override=prompt)
    out = run.ROOT / kind / 'runs/smoke' / case['id']
    assert result['status'] == 'complete' and result['submitted'], result
    assert result['requests_after_submit'] == 0, result
    assert (out / 'workspace/probe.txt').read_text().strip() == '323'
    assert (out / 'workspace/fused.txt').read_text().strip() == '323'
    loaded = json.loads((out / 'workspace/.pi/loaded-runtime.json').read_text())
    assert loaded['high'] == (kind == 'type3') and loaded['config'] == run.FLAGS
    tools = {tool['name']: tool['parameters'] for tool in loaded['tools']}
    assert all(name in tools for name in ('python', 'predict_boltz', 'predict_admet', 'submit', 'obs_recall', 'update_plan'))
    assert all('then_run' in tools[name]['properties'] for name in ('write', 'edit'))
    records = [json.loads(p.read_text()) for p in sorted((out / 'api').glob('*.json'))]
    assert records
    reasoning_present = False
    for record in records:
        body = record['request']
        assert body['model'] == run.MODEL and body['temperature'] == 1
        assert body['enable_thinking'] is (kind == 'type3')
        assert body.get('reasoning_effort') == ('high' if kind == 'type3' else None)
        assert 'max_tokens' not in body
        assert record['response']['model'] == run.MODEL
        message = record['response']['choices'][0]['message']
        reasoning_present |= bool(message.get('reasoning_content'))
    if kind == 'type3':
        assert reasoning_present, 'No upstream reasoning content observed in high mode'
    report = {'passed': True, 'kind': kind, 'model': run.MODEL, 'temperature': 1,
              'enable_thinking': kind == 'type3', 'reasoning_effort': 'high' if kind == 'type3' else None,
              'upstream_reasoning_observed': reasoning_present, 'all_four_mechanisms': True,
              'original_scientific_budget_guards': True, 'hidden_files_unmounted': True,
              'submit_ends_episode_without_extra_model_call': True, 'time': time.time()}
    dump(run.ROOT / kind / 'preflight/result.json', report)
    print(json.dumps(report), flush=True)
    return report


if __name__ == '__main__':
    import sys
    check(sys.argv[1])
