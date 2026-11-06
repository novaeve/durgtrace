"""Durable tmux launcher and read-only status for the prompt ablation."""
import argparse
import datetime
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PYTHON = '/data2/chenfuxin/chatdrug_generalization_20260920/venv/bin/python'
SESSIONS = {lane: 'prompt-align-bailian-' + lane + '-20261006' for lane in ['pair', 'agentdrug']}


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
        process = subprocess.run([PYTHON, '-u', str(ROOT/'run.py'), 'run', '--lane', lane, '--workers', '2'],
                                 stdout=logfile, stderr=subprocess.STDOUT)
    (ROOT/('exit_' + lane + '.json')).write_text(json.dumps({
        'exit_code': process.returncode, 'finished_utc': timestamp()}))
    sys.exit(process.returncode)


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
