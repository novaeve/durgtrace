"""Native SoL-Pi with the frozen SMDD scientific tools and benchmark-specific API."""
from pathlib import Path
import http.server
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import runtime
from runtime import Executor, dump
from api_factory import create as create_api
from agent_harness.config import AgentConfig
from agent_harness.prompts import TOOL_SCHEMAS, build_system_prompt

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
SOL = HOME / 'SoL-Pi'
MODEL = 'deepseek-v4.1-flash'
FLAGS = dict(version=1, actionFusion=True, observationPack=True,
             evidencePreservingReducer=True, onlineContextCompact=True,
             evidencePreservingReducerProvider='smdd-deepseek',
             evidencePreservingReducerModel=MODEL, cacheWriteReadRatio=12.5)


def guard(name, inputs):
    protected = ('.agent/', '.pi/session.jsonl', '.pi/loaded-runtime.json')
    if name in ('read', 'write', 'edit', 'grep', 'find', 'ls') and inputs.get('path'):
        path = str(inputs['path'])
        if '..' in Path(path).parts or (path.startswith('/') and not path.startswith('/workspace/')):
            return 'Use only the task workspace.'
        relative = path.removeprefix('/workspace/').removeprefix('./')
        if name in ('write', 'edit') and any(relative.startswith(p) for p in protected):
            return 'Runtime configuration and session evidence are managed externally.'
    commands = []
    if name == 'bash':
        commands.append(str(inputs.get('command', '')))
    if inputs.get('then_run'):
        follow = inputs['then_run']
        commands.append(str(follow.get('command', '') if isinstance(follow, dict) else follow))
    for command in commands:
        if any(c in command for c in (';', '&', '|', '`', '$', '\n', '>', '<')):
            return 'Use the SMDD python tool for computation; native shell is limited to file inspection.'
        try:
            parts = shlex.split(command)
        except ValueError:
            return 'Invalid file inspection command.'
        if not parts or parts[0] not in ('wc', 'cat', 'head', 'tail', 'ls', 'test'):
            return 'Use the original SMDD python tool for computation.'
        if any('..' in Path(p).parts or (p.startswith('/') and not p.startswith('/workspace/'))
               or '.agent' in p or '.pi/session' in p for p in parts[1:]):
            return 'Inspect only ordinary files in the current workspace.'
    return None


class Boundary:
    def __init__(self, kind, out, work):
        self.kind, self.out, self.work = kind, out, work
        self.api = create_api(kind, out)
        self.executor = Executor(str(work), AgentConfig(model='openai/' + MODEL))
        self.api_lock, self.tool_lock = threading.Lock(), threading.Lock()
        self.submitted, self.error, self.tools = False, None, 0
        self.truncations, self.requests_after_submit = 0, 0

    def service(self):
        state = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, obj, status=200):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                    if self.path == '/mcp':
                        params = body.get('params', {})
                        name, args = params['name'], params.get('arguments', {})
                        if name == 'protocol_guard':
                            reason = guard(args['name'], args.get('input') or {})
                            with (state.out / 'guard_events.jsonl').open('a') as f:
                                f.write(json.dumps({'tool': args['name'], 'reason': reason, 'time': time.time()}) + '\n')
                            text = json.dumps({'reason': reason})
                        else:
                            with state.tool_lock:
                                if name not in [tool['name'] for tool in TOOL_SCHEMAS]:
                                    raise ValueError('Unknown scientific tool')
                                if state.submitted:
                                    raise ValueError('Task already submitted')
                                state.tools += 1
                                started = time.time()
                                text, extra = state.executor.dispatch(name, args)
                                if name == 'submit' and text.startswith('Submission accepted:'):
                                    state.submitted = True
                                dump(state.out / 'tools' / f'{state.tools:03d}.json',
                                     {'name': name, 'arguments': args, 'result': text, 'extra': extra,
                                      'started': started, 'ended': time.time()})
                        self.send({'jsonrpc': '2.0', 'id': body.get('id'),
                                   'result': {'content': [{'type': 'text', 'text': text}]}})
                        return
                    if self.path != '/v1/chat/completions':
                        self.send({'error': {'message': 'Unknown endpoint'}}, 404)
                        return
                    with state.api_lock:
                        if state.submitted:
                            state.requests_after_submit += 1
                            self.send({'error': {'message': 'Task already submitted'}}, 400)
                            return
                        if state.api.calls >= 100 or state.api.total_tokens >= 10000000:
                            state.error = 'budget_exhausted'
                            self.send({'error': {'message': 'SMDD shared model budget exhausted'}}, 400)
                            return
                        data = state.api.complete(body['messages'], tools=body.get('tools'), temperature=1)
                        if data.get('model') != MODEL:
                            raise RuntimeError('Provider model mismatch')
                        if data['choices'][0].get('finish_reason') == 'length':
                            state.truncations += 1
                            self.send({'error': {'message': 'Provider output truncated; no truncated tool call executed'}}, 400)
                            return
                    if not body.get('stream'):
                        self.send(data)
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    delta = dict(data['choices'][0]['message'])
                    if delta.get('tool_calls'):
                        delta['tool_calls'] = [dict(tool, index=i) for i, tool in enumerate(delta['tool_calls'])]
                    chunk = {'id': data['id'], 'object': 'chat.completion.chunk',
                             'created': data.get('created', int(time.time())), 'model': data['model'],
                             'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}
                    self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                    chunk['choices'] = [{'index': 0, 'delta': {}, 'finish_reason': data['choices'][0].get('finish_reason', 'stop')}]
                    chunk['usage'] = data.get('usage', {})
                    self.wfile.write(('data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n').encode())
                    self.wfile.flush()
                    self.close_connection = True
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    state.error = type(exc).__name__ + ': ' + str(exc)
                    dump(state.out / 'boundary_error.json', {'error': state.error, 'traceback': traceback.format_exc()})
                    try:
                        self.send({'error': {'message': state.error}}, 500)
                    except OSError:
                        pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


def prepare_workspace(work):
    (work / '.agent').mkdir(parents=True, exist_ok=True)
    (work / '.pi').mkdir(exist_ok=True)
    dump(work / '.agent/sol-pi.json', FLAGS)
    dump(work / '.agent/settings.json', {'quietStartup': True, 'packages': ['/opt/sol-pi'],
                                       'compaction': {'enabled': True}, 'retry': {'enabled': True, 'maxRetries': 3}})
    for name in ('rg', 'fd'):
        destination = work / '.agent/bin' / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(HOME / '.pi/agent/bin' / name, destination)


def sandbox(kind, work, port):
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--cap-drop', 'ALL']
    for path in ('/usr', '/bin', '/lib', '/lib64', '/etc'):
        cmd += ['--ro-bind', path, path]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/home', '--dir', '/home/agent',
            '--ro-bind', str(SOL), '/opt/sol-pi', '--ro-bind', '/opt/codex-node', '/opt/codex-node',
            '--ro-bind', str(ROOT / 'bridge'), '/opt/bridge',
            '--ro-bind', str(HOME / '.local/share/sol-pi-deps'), str(HOME / '.local/share/sol-pi-deps'),
            '--bind', str(work), '/workspace', '--bind', str(work / '.agent'), '/agent',
            '--chdir', '/workspace', '--clearenv']
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/agent',
           'PI_CODING_AGENT_DIR': '/agent', 'PI_OFFLINE': '1',
           'SMDD_BOUNDARY_URL': f'http://127.0.0.1:{port}',
           'SMDD_THINKING': 'high' if kind == 'type3' else 'off',
           'OPENSSL_CONF': '/dev/null', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    for key, value in env.items():
        cmd += ['--setenv', key, value]
    return cmd


def command(kind, work, port, models=False):
    cmd = sandbox(kind, work, port) + ['/opt/codex-node/bin/node',
        '/opt/sol-pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js',
        '--offline', '--approve', '--no-extensions', '--no-skills', '--no-prompt-templates',
        '--no-themes', '--no-context-files', '-e', '/opt/bridge/smdd.ts',
        '-e', '/opt/sol-pi/src/sol-pi/index.ts', '--provider', 'smdd-deepseek',
        '--model', MODEL, '--thinking', 'high' if kind == 'type3' else 'off']
    if models:
        return cmd + ['--list-models', MODEL]
    return cmd + ['--mode', 'json', '--print', '--session', '/workspace/.pi/session.jsonl',
                  '--append-system-prompt', build_system_prompt(AgentConfig(model='openai/' + MODEL))]


def classify(submitted, returncode, events, timed_out, error, truncations):
    if submitted:
        return 'complete'
    if timed_out:
        return 'timeout'
    if error == 'budget_exhausted':
        return 'budget_exhausted'
    messages = [e['message'] for e in events if e.get('type') == 'message_end'
                and e.get('message', {}).get('role') == 'assistant']
    final = messages[-1] if messages else {}
    if truncations and 'truncated' in final.get('errorMessage', ''):
        return 'provider_limit'
    if returncode == 0 and final.get('stopReason') == 'stop':
        return 'complete'
    return 'infrastructure_error'


def job(kind, case, stage='full', prompt_override=None):
    out = ROOT / kind / 'runs' / ('solpi' if stage == 'full' else stage) / case['id']
    work = out / 'workspace'
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'result.json').exists():
        return json.loads((out / 'result.json').read_text())
    if work.exists():
        raise RuntimeError('Existing unfinished attempt; inspect before restarting')
    prepare_workspace(work)
    for name, digest in case['public_hashes'].items():
        source = ROOT / kind / 'public_inputs' / case['id'] / name
        assert __import__('hashlib').sha256(source.read_bytes()).hexdigest() == digest
        shutil.copy2(source, work / name)
    prompt = f"## Task\n\n{case['description']}\n\nYour workspace at /workspace contains the task files. Start by examining them."
    if prompt_override is not None:
        prompt = prompt_override
    (out / 'prompt.txt').write_text(prompt)
    boundary = Boundary(kind, out, work)
    server = boundary.service()
    started, proc, timed_out = time.time(), None, False
    cmd = command(kind, work, server.server_port)
    dump(out / 'started.json', {'time': started, 'command': cmd, 'public_hashes': case['public_hashes']})
    try:
        with (out / 'events.jsonl').open('w') as log, (out / 'stderr.log').open('w') as err:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=err, text=True, start_new_session=True)
            dump(out / 'process.json', {'pid': proc.pid, 'started': started})
            try:
                proc.communicate(input=prompt, timeout=3600 if kind == 'type2' else 86400)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        events = []
        for line in (out / 'events.jsonl').read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        status = classify(boundary.submitted, proc.returncode, events, timed_out, boundary.error, boundary.truncations)
        filename = 'solution.csv' if kind == 'type2' else 'solution.smi'
        prediction = work / filename
        if prediction.is_file():
            assert prediction.resolve().is_relative_to(work.resolve())
            shutil.copy2(prediction, out / filename)
        result = {'task': case['id'], 'kind': kind, 'method': 'solpi', 'model': MODEL,
                  'temperature': 1, 'enable_thinking': kind == 'type3',
                  'reasoning_effort': 'high' if kind == 'type3' else None,
                  'status': status, 'submitted': boundary.submitted,
                  'has_solution': (out / filename).exists(), 'exit_code': proc.returncode,
                  'calls': boundary.api.calls, 'tokens': boundary.api.total_tokens,
                  'tool_calls': boundary.tools, 'boltz_calls': boundary.executor.boltz_calls,
                  'admet_calls': boundary.executor.admet_calls, 'provider_truncations': boundary.truncations,
                  'requests_after_submit': boundary.requests_after_submit,
                  'boundary_error': boundary.error, 'started': started, 'ended': time.time()}
    except Exception as exc:
        (out / 'error.log').write_text(traceback.format_exc())
        result = {'task': case['id'], 'kind': kind, 'method': 'solpi',
                  'status': 'infrastructure_error', 'error': type(exc).__name__}
    finally:
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        server.shutdown()
        server.server_close()
    dump(out / 'result.json', result)
    print(json.dumps(result), flush=True)
    return result
