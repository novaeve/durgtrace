from pathlib import Path
import collections
import json
import shutil
import subprocess
import run

EXPECTED_CASE_SHA = 'da312e6665807008cc758ba97e6f4289ce4501e3b1d5c82e5f540ac4ed845f6e'
EXPECTED_SCORE_SHA = 'cba1f47d76db3e606f7cef28390f71101b99936a83aeb876e5522319267fc189'
root, source = run.ROOT, run.BASELINE
assert not (root / 'runs').exists(), 'Existing experiment; do not prepare over it'
assert run.sha(source / 'cases.json') == EXPECTED_CASE_SHA
assert run.sha(source / 'score.py') == EXPECTED_SCORE_SHA
shutil.copy2(source / 'cases.json', root / 'cases.json')
shutil.copy2(source / 'score.py', root / 'score.py')
rows = run.cases()
counts = dict(collections.Counter(c['bench'] for c in rows))
assert counts == {'S2_MolEdit': 1500, 'S2_MolCustom': 1500,
                  'MolLang_edit': 400, 'MolLang_generation': 400}
assert len({c['id'] for c in rows}) == 3800
bridge_link = root / 'bridge/node_modules'
if not bridge_link.is_symlink():
    bridge_link.symlink_to('/opt/sol-pi/node_modules', target_is_directory=True)
package = json.loads((run.SOL / 'node_modules/@earendil-works/pi-coding-agent/package.json').read_text())
frozen_inputs = [run.LANG / 'data/answers.json', run.LANG / 'data/cases.json',
                 run.LANG / 'upstream/MolLangBench-main/scripts/evaluate_results.py',
                 run.S2 / 'benchmark.py', run.S2 / 'source/s2_properties.py']
frozen_inputs += list((run.S2 / 'data').glob('*.csv'))
manifest = {'method': 'sol-pi', 'model': run.MODEL, 'temperature': 0, 'enable_thinking': False,
            'reasoning_effort': None, 'credential_source': '/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env',
            'max_tokens_policy': 'omitted upstream, matching inspected Codex baseline',
            'source_case_sha256': EXPECTED_CASE_SHA, 'same_cases_as': str(source / 'cases.json'),
            'case_count': 3800, 'counts': counts, 'workers': run.WORKERS,
            'limits': {'wall_seconds': run.WALL_SECONDS, 'idle_seconds': run.IDLE_SECONDS},
            'sol_pi_git_commit': subprocess.check_output(['git', '-C', str(run.SOL), 'rev-parse', 'HEAD'], text=True).strip(),
            'pi_version': package['version'], 'sol_pi_flags': run.FLAGS,
            'sol_source_hashes': {str(p.relative_to(run.SOL)): run.sha(p) for p in (run.SOL / 'src').rglob('*.ts')},
            'source_hashes': {str(p.relative_to(root)): run.sha(p) for p in list(root.glob('*.py')) + list((root / 'bridge').glob('*.ts'))},
            'baseline_files': {str(p): run.sha(p) for p in [source / 'run.py', source / 'score.py', source / 'cases.json', source / 'launch_proxy.py']},
            'frozen_inputs': {str(p): run.sha(p) for p in frozen_inputs},
            'gold_access': 'host-only offline scorer; hidden files not mounted in native agent',
            'parser': 'unique final answer, same reviewed Codex parser including <- dative bonds',
            'budget_policy': 'one native episode per case, no correctness-selected retries',
            'stream_policy': 'same upstream streaming API; complete stream buffered before native SDK, rejecting length-truncated tools',
            'cost_metadata': 'adapter placeholders and default cache ratio; no provider billing claim'}
run.dump(root / 'manifest.json', manifest)
print(json.dumps({'prepared': True, 'count': 3800, 'counts': counts, 'pi_version': package['version']}))
