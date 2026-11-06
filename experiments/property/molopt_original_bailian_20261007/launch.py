"""Durable launcher for the original-protocol Bailian rerun."""
import argparse
import datetime
import json
from pathlib import Path
import shlex
import subprocess
import sys
import shutil
import time

ROOT = Path(__file__).resolve().parent
PYTHON = '/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python'
SESSIONS = {lane: 'molopt-original-bailian-' + lane + '-20261007' for lane in ['pair', 'agentdrug']}


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def status():
    result = {}
    for lane, session in SESSIONS.items():
        state_path = ROOT/('state_' + lane + '.json')
        summary_path = ROOT/('summary_' + lane + '.json')
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        active = subprocess.run(['tmux', 'has-session', '-t', session], capture_output=True).returncode == 0
        result[lane] = {'session': session, 'active': active, 'state': state,
                        'processed': summary.get('processed', {}), 'errors': len(summary.get('errors', [])),
                        'pilot_gate': json.loads((ROOT/('pilot_gate_'+lane+'.json')).read_text())
                        if (ROOT/('pilot_gate_'+lane+'.json')).exists() else None}
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


def launch():
    validation = json.loads((ROOT/'validation.json').read_text())
    assert validation['passed']
    for lane, session in SESSIONS.items():
        active = subprocess.run(['tmux', 'has-session', '-t', session], capture_output=True).returncode == 0
        state_path = ROOT/('state_' + lane + '.json')
        if state_path.exists() and json.loads(state_path.read_text()).get('state') in ['finished', 'halted']:
            continue
        if not active:
            cmd = shlex.join([PYTHON, '-u', str(ROOT/'launch.py'), 'worker', '--lane', lane])
            subprocess.run(['tmux', 'new-session', '-d', '-s', session, cmd], check=True)
    status()


def worker(lane):
    with (ROOT/('log_' + lane + '.txt')).open('a', buffering=1) as logfile:
        logfile.write('\nStarted ' + timestamp() + '\n')
        code = 1
        for recovery_round in range(21):
            process = subprocess.run([PYTHON, '-u', str(ROOT/'run.py'), 'run', '--lane', lane, '--workers', '2'],
                                     stdout=logfile, stderr=subprocess.STDOUT)
            code = process.returncode
            report = json.loads((ROOT/('summary_'+lane+'.json')).read_text()) if (ROOT/('summary_'+lane+'.json')).exists() else {}
            transient = lambda error: error in ['TRANSPORT_ERROR', 'HTTP_408', 'HTTP_429', 'HTTP_500', 'HTTP_502', 'HTTP_503', 'HTTP_504', 'HTTP_529']
            failed = {e['id']: e['error'] for e in report.get('errors', []) if transient(e.get('error'))}
            permanent = [e for e in report.get('errors', []) if not transient(e.get('error'))]
            state = json.loads((ROOT/('state_'+lane+'.json')).read_text()) if (ROOT/('state_'+lane+'.json')).exists() else {}
            if not failed or recovery_round == 20 or (code and permanent):
                break
            if code and state.get('reason') not in ['CONSECUTIVE_INFRASTRUCTURE_ERRORS', 'Pilot has runtime failures; inspect preserved diagnostics before continuing.']:
                break
            logfile.write('Waiting for network recovery; '+str(len(failed))+' uncompleted cases retained.\n')
            (ROOT/('state_'+lane+'.json')).write_text(json.dumps({
                'state': 'waiting_for_api_network', 'failed_cases': len(failed),
                'recovery_round': recovery_round+1, 'updated_utc': timestamp()}))
            if not wait_for_network():
                code = 1
                break
            archive = ROOT/'network_recoveries'/(lane+'_'+str(recovery_round+1)+'_'+str(int(time.time())))
            archive.mkdir(parents=True)
            known = {c['id'] for c in json.loads((ROOT/'cases.json').read_text())}
            for case_id, error in failed.items():
                assert case_id in known and '/' not in case_id
                native = ROOT/'native'/lane/case_id
                target = archive/'native'/case_id
                target.mkdir(parents=True)
                assert native.resolve().is_relative_to(ROOT.resolve())
                shutil.copy2(native/'api_calls.json', target/'api_calls.json')
                (native/'result.json').rename(target/'result.json')
                methods = ['ChatDrug', 'DeepSeek_direct'] if lane=='pair' else ['AgentDrug']
                for method in methods:
                    result = ROOT/'runs'/method/case_id/'result.json'
                    if result.exists() and json.loads(result.read_text())['status']=='error':
                        destination = archive/'runs'/method/case_id/'result.json'
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        result.rename(destination)
            logfile.write('Network recovered; resume with completed responses reused.\n')
    (ROOT/('exit_' + lane + '.json')).write_text(json.dumps({
        'exit_code': code, 'finished_utc': timestamp()}))
    sys.exit(code)


def wait_for_network():
    # This is task-local recovery; no system DNS or networking configuration changes.
    sys.path.insert(0, '/data2/chenfuxin/chatdrug_generalization_20260920')
    from provider import config
    import requests
    cfg = config()
    for attempt in range(120):
        time.sleep(60)
        try:
            response = requests.get(cfg['base_url'].rstrip('/')+'/models',
                                    headers={'Authorization': 'Bearer '+cfg['api_key']}, timeout=(10, 15))
            healthy = response.status_code == 200
            response.close()
            if healthy:
                return True
        except requests.RequestException:
            pass
    return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['launch', 'worker', 'status'])
    parser.add_argument('--lane', choices=list(SESSIONS))
    args = parser.parse_args()
    if args.command == 'status':
        status()
    elif args.command == 'launch':
        launch()
    else:
        assert args.lane
        worker(args.lane)
