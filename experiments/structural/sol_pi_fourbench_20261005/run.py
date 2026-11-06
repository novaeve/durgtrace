"""Native SoL-Pi on the exact four-benchmark frozen cases and offline evaluators."""
import ast
import collections
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from relay import Relay, MODEL

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
BASELINE = HOME / 'codex_fourbench_20261002'
SOL = HOME / 'SoL-Pi'
MOL = HOME / 'molclaw_20260924'
S2 = HOME / 's2_edit_custom_20260928'
LANG = HOME / 'mollangbench_20260928'
OLD = HOME / 'smdd_codex_type2_bailian_20260929'
FLAGS = dict(version=1, actionFusion=True, observationPack=True,
             evidencePreservingReducer=True, onlineContextCompact=True,
             evidencePreservingReducerProvider='fourbench-deepseek',
             evidencePreservingReducerModel=MODEL, cacheWriteReadRatio=12.5)
WALL_SECONDS, IDLE_SECONDS, WORKERS = 3600, 1800, 2


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path, names, ns):
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)


def cases():
    return json.loads((ROOT / 'cases.json').read_text())


def parse(text):
    # Same unique-answer parser as the reviewed Codex baseline, including dative bonds.
    tags = re.findall(r'<answer>\s*(.*?)\s*</answer>', text, re.S | re.I)
    if len(tags) != 1 or '<summary>' in text.lower():
        return None
    answer = tags[0].strip()
    if answer.startswith('<smiles>') and answer.endswith('</smiles>'):
        answer = answer[8:-9].strip()
    return answer if answer and not any(c.isspace() for c in answer) and '<' not in answer.replace('<-', '') else None


def sandbox(work, port):
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--cap-drop', 'ALL']
    paths = [Path(p) for p in ['/usr', '/bin', '/lib', '/lib64', '/etc', '/opt/codex-node']]
    paths += [MOL / 'isolated_env', HOME / 'chatdrug_generalization_20260920/venv', OLD / 'deps']
    for path in paths:
        if path.exists():
            cmd += ['--ro-bind', str(path), str(path)]
    cmd += ['--ro-bind', str(SOL), '/opt/sol-pi',
            '--ro-bind', str(ROOT / 'bridge'), '/opt/bridge',
            '--ro-bind', str(HOME / '.local/share/sol-pi-deps'), str(HOME / '.local/share/sol-pi-deps'),
            '--ro-bind', '/usr/bin/python3.10', '/data2/chenfuxin/smdd-boltz-env/bin/python',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/home', '--dir', '/root',
            '--dir', '/home/agent', '--bind', str(work), '/workspace',
            '--bind', str(work / '.agent'), '/agent', '--chdir', '/workspace', '--clearenv']
    env = {'HOME': '/home/agent', 'PI_CODING_AGENT_DIR': '/agent', 'PI_OFFLINE': '1',
           'PATH': str(MOL / 'isolated_env/bin') + ':/usr/local/bin:/usr/bin:/bin',
           'PYTHONPATH': str(OLD / 'deps'), 'FOURBENCH_BOUNDARY_URL': f'http://127.0.0.1:{port}',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'OPENSSL_CONF': '/dev/null'}
    for key, value in env.items():
        cmd += ['--setenv', key, value]
    return cmd


def command(work, port, models=False):
    cmd = sandbox(work, port) + ['/opt/codex-node/bin/node',
        '/opt/sol-pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js',
        '--offline', '--approve', '--no-extensions', '--no-skills', '--no-prompt-templates',
        '--no-themes', '--no-context-files', '-e', '/opt/bridge/fourbench.ts',
        '-e', '/opt/sol-pi/src/sol-pi/index.ts', '--provider', 'fourbench-deepseek',
        '--model', MODEL, '--thinking', 'off']
    if models:
        return cmd + ['--list-models', MODEL]
    return cmd + ['--mode', 'json', '--print', '--session', '/workspace/.pi/session.jsonl']


def prepare_workspace(work):
    (work / '.agent').mkdir(parents=True, exist_ok=True)
    (work / '.pi').mkdir(exist_ok=True)
    dump(work / '.agent/sol-pi.json', FLAGS)
    dump(work / '.agent/settings.json', {'quietStartup': True, 'compaction': {'enabled': True},
                                        'retry': {'enabled': True, 'maxRetries': 3}})
    for name in ('rg', 'fd'):
        source = HOME / '.pi/agent/bin' / name
        target = work / '.agent/bin' / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)


def final_outcome(returncode, events, timed_out, truncations):
    assistants = [e['message'] for e in events if e.get('type') == 'message_end'
                  and e.get('message', {}).get('role') == 'assistant']
    final = assistants[-1] if assistants else {}
    text = ''.join(block.get('text', '') for block in final.get('content', []) if block.get('type') == 'text')
    # Intermediate aborts followed by native compaction/resumption are not failures.
    if timed_out:
        status = 'timeout'
    elif returncode == 0 and final.get('stopReason') == 'stop':
        status = 'complete'
    elif truncations and 'truncated' in final.get('errorMessage', ''):
        status = 'provider_limit'
    else:
        status = 'error'
    return status, text, final.get('errorMessage')


def execute(case, stage, prompt_override=None):
    out = ROOT / 'runs' / stage / case['id']
    work = ROOT / 'work' / stage / case['id']
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'result.json').exists():
        return json.loads((out / 'result.json').read_text())
    if (out / 'started.json').exists():
        row = {'id': case['id'], 'bench': case['bench'], 'bucket': case['bucket'],
               'status': 'interrupted', 'candidate': None, 'method': 'sol-pi'}
        dump(out / 'result.json', row)
        return row
    prepare_workspace(work)
    # Identical task prompt to the Codex fourbench baseline.
    query = case['prompt'].replace('<smiles>', '<answer>').replace('</smiles>', '</answer>')
    prompt = query + '\n\nWork only in /workspace. Python with RDKit is available for your own structural calculations. Do not access hidden answers, evaluators, prior experiment results, or other task directories. Submit exactly ONE final molecule as <answer>SMILES</answer> in your final response.'
    if prompt_override is not None:
        prompt = prompt_override
    (out / 'prompt.txt').write_text(prompt)
    started = time.time()
    relay = Relay(out)
    server = relay.service()
    proc, timed_out, timeout_reason = None, False, None
    cmd = command(work, server.server_port)
    dump(out / 'started.json', {'started': started, 'command': cmd})
    try:
        with (out / 'events.jsonl').open('w') as log, (out / 'stderr.log').open('w') as err:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=err,
                                    text=True, start_new_session=True)
            dump(out / 'process.json', {'pid': proc.pid, 'started': started})
            first = True
            while True:
                try:
                    proc.communicate(input=prompt if first else None, timeout=20)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    now = time.time()
                    idle = now - max(started, (out / 'events.jsonl').stat().st_mtime)
                    if now - started > WALL_SECONDS or idle > IDLE_SECONDS:
                        timed_out = True
                        timeout_reason = 'wall_3600s' if now - started > WALL_SECONDS else 'idle_1800s'
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                        break
        events = []
        for line in (out / 'events.jsonl').read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        status, text, error = final_outcome(proc.returncode, events, timed_out, relay.truncations)
        records = [json.loads(p.read_text()) for p in sorted((out / 'api').glob('*.json'))]
        usage = collections.Counter()
        for record in records:
            for key, value in (record.get('response', {}).get('usage') or {}).items():
                if isinstance(value, (int, float)):
                    usage[key] += value
        tool_calls = sum(e.get('type') == 'tool_execution_end' for e in events)
        row = {'id': case['id'], 'bench': case['bench'], 'bucket': case['bucket'],
               'status': status, 'candidate': parse(text) if status == 'complete' else None,
               'output': text, 'method': 'sol-pi', 'model': MODEL, 'returncode': proc.returncode,
               'error': error, 'timeout_reason': timeout_reason, 'usage': dict(usage),
               'llm_requests': len(records), 'provider_truncations': relay.truncations,
               'tool_calls': tool_calls, 'seconds': time.time() - started}
    except Exception as exc:
        (out / 'exception.log').write_text(traceback.format_exc())
        row = {'id': case['id'], 'bench': case['bench'], 'bucket': case['bucket'],
               'status': 'error', 'candidate': None, 'method': 'sol-pi', 'error': type(exc).__name__}
    finally:
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        server.shutdown()
        server.server_close()
    dump(out / 'result.json', row)
    print(json.dumps({k: row.get(k) for k in ('id', 'status', 'tool_calls', 'candidate')}), flush=True)
    return row


def summary(stage, selected):
    rows = [json.loads(p.read_text()) for p in (ROOT / 'runs' / stage).glob('*/result.json')]
    groups = {}
    for bench, count in collections.Counter(c['bench'] for c in selected).items():
        rr = [r for r in rows if r['bench'] == bench]
        groups[bench] = {'expected': count, 'processed': len(rr),
                         'runtime_errors': sum(r['status'] not in ('complete', 'provider_limit', 'timeout') for r in rr),
                         'status_counts': dict(collections.Counter(r['status'] for r in rr)),
                         'missing_submission': sum(not r.get('candidate') for r in rr)}
    report = {'processed': len(rows), 'expected': len(selected), 'groups': groups, 'updated': time.time()}
    dump(ROOT / 'runs' / stage / 'summary.json', report)
    return report


def main(stage):
    selected = cases()
    if stage == 'pilot':
        selected = [c for c in selected if c['index'] == 0]
    with (ROOT / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        summary(stage, selected)
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            futures = [pool.submit(execute, c, stage) for c in selected]
            for future in concurrent.futures.as_completed(futures):
                future.result()
                summary(stage, selected)
    return summary(stage, selected)


if __name__ == '__main__':
    main(sys.argv[1])
