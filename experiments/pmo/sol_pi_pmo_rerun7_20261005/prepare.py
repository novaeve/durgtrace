"""Prepare an isolated fresh rerun without changing the original experiment."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

root = Path(__file__).resolve().parent
source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.home() / 'sol_pi_pmo_20261004'
expected = '973eae2a4e5020ce6c9568ea8919e7dafc599c5a39b38af0cedfbd507192358f'
actual = hashlib.sha256((source / 'run.py').read_bytes()).hexdigest()
assert actual == expected, (actual, expected)
assert not (root / 'control').exists(), 'Rerun already initialized; do not overwrite it'
text = (source / 'run.py').read_text(encoding='utf-8')
text = text.replace('from stall_watchdog import run_native\n',
                    'from stall_watchdog import run_native\nfrom segment_policy import outcome\n', 1)
start = text.index("            if proc.stalled: return finish(")
end = text.index("            if not (work / '.pi/session.jsonl').exists()", start)
text = text[:start] + '''            texts = [''.join(block.get('text', '') for block in event['message'].get('content', []) if block.get('type') == 'text')
                     for event in events if event.get('type') == 'message_end' and event.get('message', {}).get('role') == 'assistant']
            matches = re.findall(r'<answer>\\s*(.*?)\\s*</answer>', texts[-1] if texts else '', re.S)
            answer = canonical(matches[-1]) if len(matches) == 1 else None
            ledger = boundary.oracle.ledger()
            decision = outcome(proc, events, boundary.truncations, before, ledger.exhausted, answer in ledger.buffer)
            append(out / 'segment_decisions.jsonl', dict(segment=segment, returncode=proc.returncode,
                   decision=decision, truncations=boundary.truncations, submissions=len(ledger.rows)))
            if decision == 'stalled':
                return finish(out, task, boundary, 'skipped_stalled', reason='30 minutes without a complete scored submission')
            if decision == 'completed':
                return finish(out, task, boundary, 'completed', answer)
            if decision == 'provider_limit':
                return finish(out, task, boundary, 'partial_provider_limit', reason='three provider length truncations')
            if decision == 'retry_truncation':
                continue
            if decision == 'error':
                errors = [event.get('message', {}) for event in events if event.get('type') == 'message_end'
                          and event.get('message', {}).get('role') == 'assistant'
                          and event.get('message', {}).get('stopReason') == 'error']
                raise RuntimeError('Native Pi failed: ' + json.dumps(errors[-1:], ensure_ascii=False)[:1200]
                                   + '; stderr: ' + (out / f'stderr_{segment:04d}.log').read_text()[-1200:])
''' + text[end:]
assert text.count('def suite(stage):') == 1
text = text.replace('def suite(stage):', 'def suite(stage, tasks=None):')
text = text.replace("    tasks = list(TASKS) if stage == 'full' else PILOT_TASKS",
                    "    tasks = list(tasks) if tasks is not None else (list(TASKS) if stage == 'full' else PILOT_TASKS)")
text = text.replace("planned=23 if stage == 'full' else len(PILOT_TASKS)",
                    "planned=7 if stage == 'full' else len(PILOT_TASKS)")
compile(text, str(root / 'run.py'), 'exec')
(root / 'run.py').write_text(text, encoding='utf-8')
shutil.copy2(source / 'status.py', root / 'status.py')
status = (root / 'status.py').read_text().replace("str(root / 'run.py').encode()", "str(root / 'runner.py').encode()")
(root / 'status.py').write_text(status, encoding='utf-8')
shutil.copytree(source / 'bridge', root / 'bridge', dirs_exist_ok=True, symlinks=True)
from segment_policy import check_policy
check = check_policy()
(root / 'policy_checks.json').write_text(json.dumps(check, indent=2))
manifest = dict(source=str(source), source_run_sha256=actual, fresh_runs=True,
                budget=1000, seed=0, concurrency=2, provider_token_policy='unchanged',
                changes=['retry provider truncation with exit code zero; maximum three',
                         'judge final assistant outcome after recovered compaction aborts'],
                original_results={p.parent.parent.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (source / 'control/full').glob('*/0/result.json')})
if len(sys.argv) == 1:
    for name in ['preflight.json', 'preflight/boundary_tests.json', 'pilot_validation.json']:
        assert json.loads((source / name).read_text())['accepted'], name
    manifest['original_preflight_accepted'] = True
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(dict(prepared=True, root=str(root), policy_checks=check)))
