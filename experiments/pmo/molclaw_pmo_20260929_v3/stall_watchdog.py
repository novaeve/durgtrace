"""Skip a task after 30 minutes without a new complete scoring record."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from types import SimpleNamespace
from trajectory import complete_auc

STALL_SECONDS = 1800


def read_prefix(control):
    path = Path(control)/'oracle_queries.jsonl'
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
            if row['index'] != len(rows)+1 or not isinstance(row['score'], (int, float)):
                break
            rows.append(row)
        except (ValueError, KeyError, TypeError):
            break
    return rows


def progress(control, now=None):
    now = time.time() if now is None else now
    path = Path(control)/'watchdog.json'
    count = len(read_prefix(control))
    state = json.loads(path.read_text()) if path.exists() else {'count':count,'last_progress':now}
    if count > state['count']:
        state = {'count':count,'last_progress':now}
    path.write_text(json.dumps(state))
    return now-state['last_progress'] >= STALL_SECONDS


def run_native(control, command, input, **kwargs):
    if progress(control):
        return SimpleNamespace(returncode=-1, stalled=True)
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, start_new_session=True, **kwargs)
    first = True
    while True:
        try:
            proc.communicate(input=input if first else None, timeout=10)
            return SimpleNamespace(returncode=proc.returncode, stalled=False)
        except subprocess.TimeoutExpired:
            first = False
            if progress(control):
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                return SimpleNamespace(returncode=proc.returncode, stalled=True)


def partial_result(control, task, reason='no complete scored submission for 30 minutes'):
    from pmo_common import dump
    control = Path(control)
    rows = read_prefix(control)
    # Preserve the original ledger, including any damaged tail, for inspection.
    dump(control/'partial_scored_rows.json', rows)
    auc, curve = complete_auc(rows, budget=len(rows)) if rows else (0.0, [])
    dump(control/'top10_trajectory.json', curve)
    best = max((r for r in rows if r.get('canonical') and r.get('status') != 'invalid'), key=lambda r:r['score'], default=None)
    result = {'method':'molclaw','task':task,'seed':0,'status':'skipped_stalled',
              'experiment_finished':False,'complete':False,'oracle_submissions':len(rows),
              'submission_budget':1000,'skip_reason':reason,'time':time.time(),
              'auc_top10_observed':auc,'auc_observed_horizon':len(rows),
              'auc_area_divided_by_1000':auc*len(rows)/1000,
              'auc_protocol':'actual recorded prefix only; observed AUC normalized by actual count; no tail fill',
              'best_observed_answer':best['canonical'] if best else None,
              'best_observed_score':best['score'] if best else None}
    dump(control/'result.json',result)
    state=json.loads((control/'state.json').read_text())
    state.update(status='skipped_stalled',skip_reason=reason)
    dump(control/'state.json',state)
    return result
