"""Native Pi + unmodified SoL-Pi PMO-1K benchmark, using Codex's exact oracle boundary."""
from pathlib import Path
import argparse
import concurrent.futures
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
BASELINE = HOME / 'codex_pmo_20261003'
SOL = HOME / 'SoL-Pi'
sys.path[:0] = [str(BASELINE / 'source_snapshot'), str(BASELINE)]
from transport import Boundary as CodexBoundary
from oracle_server import LEGACY, SUBMISSION, TASKS, canonical
from pmo_common import dump, append, sha
from trajectory import complete_auc
from stall_watchdog import run_native
from guard import reason as guard_reason, python_reason

MODEL = 'deepseek-v4.1-flash'
FLAGS = dict(version=1, actionFusion=True, observationPack=True,
             evidencePreservingReducer=True, onlineContextCompact=True,
             evidencePreservingReducerProvider='pmo-deepseek',
             evidencePreservingReducerModel=MODEL, cacheWriteReadRatio=12.5)
PILOT_TASKS = ['qed', 'amlodipine_mpo', 'celecoxib_rediscovery']


class Boundary(CodexBoundary):
    def call(self, name, args):
        if name != 'protocol_guard':
            if name == 'score_file':
                args = dict(args, file_path=args['path'].removeprefix('/workspace/'))
            elif name == 'python':
                args = dict(args, code=args['code'].replace('/workspace', str(self.work)))
            return super().call(name, args)
        tool = args['name']
        inputs = dict(args.get('input') or {})
        reason = None
        protected = {'.pi/sol-pi.json', '.pi/loaded-runtime.json'}
        if tool in {'write', 'edit'}:
            path = str(inputs.get('path', ''))
            relative = path.removeprefix('/workspace/').removeprefix('./')
            if relative.startswith('.agent/') or relative in protected:
                reason = 'The benchmark runtime configuration is managed externally.'
            if tool == 'write' and path.endswith('.py'):
                reason = reason or python_reason(inputs.get('content', ''))
        def translate(value):
            if isinstance(value, str): return value.replace('/workspace', str(self.work))
            if isinstance(value, list): return [translate(v) for v in value]
            if isinstance(value, dict): return {k: translate(v) for k, v in value.items()}
            return value
        mapped = {'read': 'Read', 'write': 'Write', 'edit': 'Edit', 'bash': 'Bash'}
        if tool in mapped:
            old = translate(inputs)
            if 'path' in old: old['file_path'] = old['path']
            reason = reason or guard_reason({'cwd': str(self.work), 'tool_name': mapped[tool], 'tool_input': old})
        if inputs.get('then_run'):
            reason = reason or guard_reason({'cwd': str(self.work), 'tool_name': 'Bash', 'tool_input': translate(inputs['then_run'])})
        append(self.out / 'guard_events.jsonl', {'time': time.time(), 'tool': tool,
               'input': inputs, 'decision': 'deny' if reason else 'allow', 'reason': reason})
        return {'reason': reason}


def command(work, boundary_port, mode='json'):
    # Only the sample workspace and public runtimes are mounted. Prior runs,
    # oracle implementation/data and the real API credential are inaccessible.
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--cap-drop', 'ALL']
    for path in ['/usr', '/bin', '/lib', '/lib64', '/etc']:
        cmd += ['--ro-bind', path, path]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
            '--dir', '/home', '--dir', '/home/agent',
            '--ro-bind', str(SOL), '/opt/sol-pi',
            '--ro-bind', '/opt/codex-node', '/opt/codex-node',
            '--ro-bind', str(ROOT / 'bridge'), '/opt/bridge',
            '--ro-bind', str(HOME / '.local/share/sol-pi-deps'), str(HOME / '.local/share/sol-pi-deps'),
            '--bind', str(work), '/workspace',
            '--bind', str(work / '.agent'), '/agent',
            '--chdir', '/workspace', '--clearenv']
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/agent',
           'PI_CODING_AGENT_DIR': '/agent', 'PI_OFFLINE': '1',
           'PMO_BOUNDARY_URL': f'http://127.0.0.1:{boundary_port}',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    for key, value in env.items(): cmd += ['--setenv', key, value]
    cmd += ['/opt/codex-node/bin/node', '/opt/sol-pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js',
            '--offline', '--approve', '--no-extensions', '--no-skills', '--no-prompt-templates',
            '--no-themes', '--no-context-files',
            '-e', '/opt/bridge/pmo.ts', '-e', '/opt/sol-pi/src/sol-pi/index.ts',
            '--provider', 'pmo-deepseek', '--model', MODEL, '--thinking', 'off']
    if mode == 'models': return cmd + ['--list-models', MODEL]
    return cmd + ['--mode', 'json', '--print', '--session', '/workspace/.pi/session.jsonl']


def finish(out, task, boundary, status, answer=None, reason=None):
    ledger = boundary.oracle.ledger()
    rows = ledger.rows
    auc, curve = complete_auc(rows, budget=len(rows)) if rows else (0.0, [])
    best = max(ledger.buffer.items(), key=lambda item: item[1][0], default=None)
    calls, usage = 0, {}
    for path in sorted((out / 'api').glob('*.json')):
        data = json.loads(path.read_text())
        response = data.get('response') or {}
        calls += 1
        for key, value in (response.get('usage') or {}).items():
            if isinstance(value, (int, float)): usage[key] = usage.get(key, 0) + value
    result = dict(method='sol-pi', model=MODEL, task=task, seed=0, status=status,
                  complete=status == 'completed', oracle_submissions=len(rows),
                  submission_budget=ledger.budget, unique_valid=len(ledger.buffer),
                  invalid=sum(row['status'] == 'invalid' for row in rows),
                  duplicates=sum(row['status'] == 'duplicate' for row in rows),
                  auc_top10=auc if len(rows) == ledger.budget else None,
                  auc_top10_observed=auc, auc_area_divided_by_1000=auc * len(rows) / ledger.budget,
                  auc_protocol='MolClaw v3 unique-valid top10 trapezoid from zero; incomplete results have no fabricated tail',
                  final_answer=answer, best_observed_answer=best[0] if best else None,
                  best_observed_score=best[1][0] if best else None,
                  llm_requests=calls, provider_usage=usage,
                  reason=reason, time=time.time())
    dump(out / 'top10_trajectory.json', curve)
    dump(out / 'result.json', result)
    return result


def job(task, stage='full', budget=1000):
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.chdir(LEGACY)
    out = ROOT / 'control' / stage / task / '0'
    work = ROOT / 'runs' / stage / task / '0'
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    lock = (out / 'run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (out / 'result.json').exists(): return json.loads((out / 'result.json').read_text())
    for path, digest in json.loads((LEGACY / 'prepared/dependencies.json').read_text()).items():
        if sha(path) != digest: raise RuntimeError('Oracle dependency changed: ' + path)
    (work / '.agent').mkdir(exist_ok=True)
    (work / '.pi').mkdir(exist_ok=True)
    dump(work / '.agent/sol-pi.json', FLAGS)
    dump(work / '.agent/settings.json', {'quietStartup': True,
         'compaction': {'enabled': True}, 'retry': {'enabled': True, 'maxRetries': 3}})
    for tool in ['rg', 'fd']:
        target = work / '.agent/bin' / tool
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            import shutil
            shutil.copy2(HOME / '.pi/agent/bin' / tool, target)
    source = SUBMISSION / 'runs/deepseek' / task / '0/answers.jsonl'
    seed = json.loads(source.read_text().splitlines()[0])
    assert seed['index'] == 1
    boundary = Boundary(out, work, task, budget)
    if not boundary.oracle.ledger().rows: boundary.oracle.score([seed['raw']], 'initialization')
    initial = boundary.oracle.ledger().rows[0]
    assert initial['raw'] == seed['raw'] and abs(initial['score'] - seed['score']) < 1e-10
    dump(out / 'config.json', dict(method='sol-pi', model=MODEL, temperature=0,
         enable_thinking=False, task=task, seed=0, oracle_budget=budget,
         initialization_source=str(source), initialization_sha256=sha(source),
         initial_smiles=seed['raw'], all_four_enabled=True, sol_pi_config=FLAGS,
         no_llm_token_budget_claim=True, code_hashes={path.name: sha(path) for path in ROOT.glob('*.py')}))
    source_prompt = BASELINE / 'control/full' / task / '0/initial_prompt.txt'
    prompt = source_prompt.read_text().replace('of 1000 shared oracle submissions', f'of {budget} shared oracle submissions').replace('exactly 1000 actual scored', f'exactly {budget} actual scored')
    if stage == 'pilot': prompt += ' This is a small independent transport and budget check. Exercise the Python tool for RDKit validation, and submit candidates through PMO tools to fill this small test budget.'
    (out / 'initial_prompt.txt').write_text(prompt)
    state_path = out / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'segment': 0, 'started': time.time()}
    server = boundary.service()
    try:
        for segment in range(state['segment'], 2048):
            ledger = boundary.oracle.ledger()
            if segment:
                prompt = f'Continue the same PMO task and single session. {len(ledger.rows)} of {budget} submissions used. Fill the remaining actual submission budget through PMO tools. At exhaustion return exactly <answer>SMILES</answer> for the best already evaluated molecule.'
            state.update(status='running', segment=segment, pid=os.getpid(), time=time.time())
            dump(state_path, state)
            (out / f'prompt_{segment:04d}.txt').write_text(prompt)
            before = boundary.truncations
            with (out / f'events_{segment:04d}.jsonl').open('w') as log, (out / f'stderr_{segment:04d}.log').open('w') as err:
                proc = run_native(out, command(work, server.server_address[1]),
                                  input=prompt, text=True, cwd=work, stdout=log, stderr=err)
            events = []
            for line in (out / f'events_{segment:04d}.jsonl').read_text().splitlines():
                try: events.append(json.loads(line))
                except ValueError: pass
            state['segment'] = segment + 1
            dump(state_path, state)
            if proc.stalled: return finish(out, task, boundary, 'skipped_stalled', reason='30 minutes without a complete scored submission')
            if boundary.truncations >= 3: return finish(out, task, boundary, 'partial_provider_limit', reason='three provider length truncations')
            if proc.returncode and boundary.truncations > before: continue
            errors = [event.get('message', {}) for event in events if event.get('type') == 'message_end' and event.get('message', {}).get('stopReason') == 'error']
            if proc.returncode or errors:
                raise RuntimeError('Native Pi failed: ' + json.dumps(errors[-1:], ensure_ascii=False)[:1200] + '; stderr: ' + (out / f'stderr_{segment:04d}.log').read_text()[-1200:])
            texts = [''.join(block.get('text', '') for block in event['message'].get('content', []) if block.get('type') == 'text')
                     for event in events if event.get('type') == 'message_end' and event.get('message', {}).get('role') == 'assistant']
            matches = re.findall(r'<answer>\s*(.*?)\s*</answer>', texts[-1] if texts else '', re.S)
            answer = canonical(matches[-1]) if len(matches) == 1 else None
            ledger = boundary.oracle.ledger()
            if ledger.exhausted and answer in ledger.buffer: return finish(out, task, boundary, 'completed', answer)
            if not (work / '.pi/session.jsonl').exists(): raise RuntimeError('Native Pi did not preserve a session')
        return finish(out, task, boundary, 'partial_agent_stop', reason='native session continuation limit')
    except Exception as exc:
        dump(out / 'exception.json', {'error': str(exc), 'traceback': traceback.format_exc()})
        return finish(out, task, boundary, 'error', reason=str(exc))
    finally:
        server.shutdown()
        server.server_close()


def summary(stage):
    rows = {path.parent.parent.name: json.loads(path.read_text())
            for path in (ROOT / 'control' / stage).glob('*/0/result.json')}
    data = dict(stage=stage, planned=23 if stage == 'full' else len(PILOT_TASKS),
                finished=len(rows), completed=sum(row['status'] == 'completed' for row in rows.values()), tasks=rows)
    dump(ROOT / f'{stage}_summary.json', data)
    return data


def suite(stage):
    tasks = list(TASKS) if stage == 'full' else PILOT_TASKS
    budget = 1000 if stage == 'full' else 10
    with (ROOT / f'{stage}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(job, task, stage, budget): task for task in tasks}
            for future in concurrent.futures.as_completed(futures):
                try: result = future.result()
                except Exception as exc:
                    out = ROOT / 'control' / stage / futures[future] / '0'
                    out.mkdir(parents=True, exist_ok=True)
                    result = dict(task=futures[future], status='setup_error', reason=str(exc), oracle_submissions=0)
                    dump(out / 'result.json', result)
                summary(stage)
                print(json.dumps({'task': futures[future], 'status': result['status'], 'oracle_submissions': result['oracle_submissions']}), flush=True)
    return summary(stage)


def validate_pilot():
    data = summary('pilot')
    failures = []
    for task in PILOT_TASKS:
        result = data['tasks'].get(task, {})
        if result.get('status') != 'completed' or result.get('oracle_submissions') != 10: failures.append(task + ': incomplete')
        out = ROOT / 'control/pilot' / task / '0'
        work = ROOT / 'runs/pilot' / task / '0'
        runtime = json.loads((work / '.pi/loaded-runtime.json').read_text()) if (work / '.pi/loaded-runtime.json').exists() else {}
        if runtime.get('provider') != 'pmo-deepseek' or runtime.get('model') != MODEL: failures.append(task + ': model/runtime mismatch')
        if runtime.get('config') != FLAGS: failures.append(task + ': SoL-Pi flags mismatch')
        receipts = [json.loads(line) for line in (out / 'mcp_receipts.jsonl').read_text().splitlines()] if (out / 'mcp_receipts.jsonl').exists() else []
        if not any(row['request']['params']['name'] == 'python' for row in receipts): failures.append(task + ': missing guarded Python')
        if not any(row['request']['params']['name'] in ['score_molecules', 'score_file'] for row in receipts): failures.append(task + ': missing scored tool call')
    report = dict(accepted=not failures, tasks=PILOT_TASKS, failures=failures, time=time.time())
    dump(ROOT / 'pilot_validation.json', report)
    return report


def aggregate():
    data = summary('full')
    baseline = json.loads((BASELINE / 'full_summary.json').read_text())
    prior = baseline.get('tasks') or baseline.get('results') or {}
    comparison = []
    for task in TASKS:
        new = data['tasks'].get(task, {})
        old = prior.get(task, {})
        comparison.append(dict(task=task, sol_pi_status=new.get('status', 'pending'),
             sol_pi_submissions=new.get('oracle_submissions', 0), sol_pi_auc=new.get('auc_top10'),
             codex_status=old.get('status'), codex_submissions=old.get('oracle_submissions'), codex_auc=old.get('auc_top10')))
    complete = [row for row in data['tasks'].values() if row.get('complete')]
    report = dict(method='sol-pi', model=MODEL, budget=1000, seeds=[0], tasks=23,
         completed=len(complete), all_tasks_completed=len(complete) == 23,
         mean_auc_complete_tasks=sum(row['auc_top10'] for row in complete) / len(complete) if complete else None,
         sum_auc_all23=sum(row.get('auc_top10') or 0 for row in data['tasks'].values()) if len(complete) == 23 else None,
         comparison=comparison, generated=time.time(), incomplete_tail_policy='no fabricated tail')
    dump(ROOT / 'pmo_1k_all23_auc.json', report)
    return report


def pipeline():
    pilot = suite('pilot')
    accepted = validate_pilot()
    print(json.dumps(accepted), flush=True)
    if not accepted['accepted']: raise SystemExit('Pilot acceptance failed; full suite was not launched')
    suite('full')
    report = aggregate()
    dump(ROOT / 'pipeline_exit.json', dict(finished=True, all_tasks_completed=report['all_tasks_completed'], time=time.time()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['pilot', 'full', 'status', 'validate-pilot', 'aggregate', 'pipeline'])
    args = parser.parse_args()
    if args.stage == 'status': print(json.dumps(summary('full')))
    elif args.stage == 'validate-pilot': print(json.dumps(validate_pilot()))
    elif args.stage == 'aggregate': print(json.dumps(aggregate()))
    elif args.stage == 'pipeline': pipeline()
    else: suite(args.stage)
