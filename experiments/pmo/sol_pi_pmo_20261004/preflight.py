import json
import subprocess
import time
import run
from pmo_common import dump, sha

root = run.ROOT
work = root / 'preflight/work'
(work / '.agent').mkdir(parents=True, exist_ok=True)
(work / '.pi').mkdir(exist_ok=True)
dump(work / '.agent/sol-pi.json', run.FLAGS)
dump(work / '.agent/settings.json', {'quietStartup': True})
command = run.command(work, 9, mode='models')
proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
(root / 'preflight/models.stdout').write_text(proc.stdout)
(root / 'preflight/models.stderr').write_text(proc.stderr)
print('MODELS_EXIT', proc.returncode)
print(proc.stdout[-1500:])
print(proc.stderr[-1500:])
assert proc.returncode == 0 and run.MODEL in proc.stdout
prefix = command[:command.index('/opt/codex-node/bin/node')]
for unavailable in [run.BASELINE, run.LEGACY, run.HOME / 'molingo_20260922/private/deepseek_canchen.env']:
    checked = subprocess.run(prefix + ['/usr/bin/test', '!', '-e', str(unavailable)], timeout=30)
    assert checked.returncode == 0, 'Unexpected data exposed in agent sandbox'
print('ISOLATION_OK')
for task in run.TASKS:
    assert (run.BASELINE / 'control/full' / task / '0/initial_prompt.txt').is_file()
    assert (run.SUBMISSION / 'runs/deepseek' / task / '0/answers.jsonl').is_file()
for path, digest in json.loads((run.LEGACY / 'prepared/dependencies.json').read_text()).items():
    assert sha(path) == digest, 'Oracle dependency mismatch'
manifest = dict(method='sol-pi', model=run.MODEL, temperature=0, enable_thinking=False,
    submission_budget=1000, seeds=[0], tasks=list(run.TASKS), concurrency=2,
    same_key_source='server-side existing Relay config; no credential copied to agent',
    same_initialization=str(run.SUBMISSION / 'runs/deepseek'),
    budget_rule='Every submitted molecule, including invalid and duplicates, consumes one submission; references and feedback are charged',
    auc_primary='MolClaw v3 complete_auc, unique-valid top10 trapezoid from zero',
    incomplete_tail='No tail fill', sol_pi_config=run.FLAGS, pi_version='0.86.1',
    sol_pi_commit=subprocess.check_output(['git', '-C', str(run.SOL), 'rev-parse', 'HEAD'], text=True).strip(),
    baseline=str(run.BASELINE),
    source_hashes={str(p): sha(p) for p in [root / 'run.py', root / 'bridge/pmo.ts',
        run.BASELINE / 'transport.py', run.BASELINE / 'source_snapshot/oracle_server.py',
        run.BASELINE / 'source_snapshot/trajectory.py', run.LEGACY / 'prepared/dependencies.json']},
    guard='Existing protocol guard applies to native file/bash tools and fused then_run; same guarded RDKit Python tool',
    stall_seconds=1800, continuation_limit=2048, provider_truncation_limit=3,
    no_llm_token_budget_claim=True, adapter_context_window=262144, adapter_max_tokens_metadata=65536,
    provider_payload_max_tokens='not forwarded, matching existing Codex Boundary.complete', created=time.time())
dump(root / 'manifest.json', manifest)
dump(root / 'preflight.json', {'accepted': True, 'models': 'PASS', 'isolation': 'PASS',
                             'oracle_dependencies': 'PASS', 'initializations': 'PASS', 'time': time.time()})
print('PREFLIGHT_OK', len(manifest['tasks']))
