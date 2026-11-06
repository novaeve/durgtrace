"""All native oracle submissions share one hard 1000-query budget.

References, parent/property feedback and final answers all enter the same ledger.
Model generations alone do not become oracle submissions until evaluated.
"""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import time
import run_editors as native
from submission_budget import SubmissionLedger, mt_mol_auc

ROOT = Path(__file__).resolve().parent
RUNS = ROOT/'runs_oracle_1k'


class OracleBudgetExhausted(BaseException):
    """Escape native broad Exception catches; transport also checks the cap."""


class UnifiedOracle:
    def __init__(self, out, evaluator, budget=1000):
        self.out = out
        self.physical_this_process = 0
        def evaluate(sm):
            self.physical_this_process += 1
            return evaluator(sm)
        self.ledger = SubmissionLedger(out/'oracle_queries.jsonl', native.canonical,
                                       evaluate, budget)
        # Replay already-written logical queries idempotently after interruption.
        self.cursor = 0

    def get(self, smiles, source):
        event = f'query/{self.cursor+1}/{source}'
        if self.cursor < len(self.ledger.rows) and self.ledger.rows[self.cursor]['event_id'] != event:
            raise RuntimeError('Oracle replay diverged from the saved call sequence')
        if self.ledger.exhausted and event not in self.ledger.events:
            raise OracleBudgetExhausted()
        row = self.ledger.submit(smiles, event)
        self.cursor += 1
        return row['score']


class Generations:
    def __init__(self, out, oracle):
        self.out, self.oracle, self.rows = out, oracle, []
    def submit(self, smiles, event_id):
        row = {'event_id': event_id, 'raw': smiles,
               'oracle_cursor_at_generation': self.oracle.cursor}
        self.rows.append(row)
        # Deterministic overwrite on replay, never a second model call.
        native.dump(self.out/'model_outputs.json', self.rows)
        return row


class BoundedRelay:
    def __init__(self, out, oracle):
        self.inner = native.Relay(out)
        self.oracle = oracle
    def complete(self, *args, **kwargs):
        # Check logical replay position, rather than persisted length, on recovery.
        if self.oracle.cursor >= self.oracle.ledger.budget:
            raise OracleBudgetExhausted()
        return self.inner.complete(*args, **kwargs)
    def usage(self):
        return self.inner.usage()


def finish_last_output(generations, oracle):
    if not generations.rows:
        return
    last = generations.rows[-1]
    sm = native.canonical(last['raw'])
    after = oracle.ledger.rows[last['oracle_cursor_at_generation']:oracle.cursor]
    # If native feedback has already queried this returned molecule, don't add
    # an evaluator-invented second query just for final reporting.
    if not any(row['canonical'] == sm for row in after):
        oracle.get(last['raw'], 'final_output')


def job(method, task):
    os.chdir(native.LEGACY)
    for path, digest in json.loads((native.LEGACY/'prepared/dependencies.json').read_text()).items():
        if native.sha(path) != digest:
            raise RuntimeError('Verified oracle dependency changed: '+path)
    out = RUNS/method/task/'0'
    out.mkdir(parents=True, exist_ok=True)
    with (out/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'result.json').exists():
            return json.loads((out/'result.json').read_text())
        seed, source = native.initial_row(task)
        config = {'method': method, 'task': task, 'model': native.run_direct.MODEL,
                  'oracle_query_budget': 1000, 'duplicate_queries_consume_budget': True,
                  'initial_source': str(source), 'initial_answer': seed['raw'],
                  'reference_queries_count': True, 'feedback_queries_count': True,
                  'workflow': 'one native editing episode; no added search',
                  'library_sha': native.sha(ROOT/f'native_data/{method}_10000.csv'),
                  'source_hashes': {p.name: native.sha(p) for p in
                                   [Path(__file__), ROOT/'run_editors.py',
                                    ROOT/'submission_budget.py']}}
        if (out/'config.json').exists():
            assert json.loads((out/'config.json').read_text()) == config
        native.dump(out/'config.json', config)
        oracle = UnifiedOracle(out, native.make_oracle(native.TASKS[task][0]))
        outputs, relay = Generations(out, oracle), BoundedRelay(out, oracle)
        native.dump(out/'progress.json', {'status': 'running', 'time': time.time()})
        try:
            oracle.get(seed['raw'], 'initial_model_answer')
            if native.canonical(seed['raw']) is None:
                status, trace = 'invalid_initial_answer', {}
            else:
                trace = {'chatdrug': native.chatdrug, 'agentdrug': native.agentdrug}[method](
                    task, seed['raw'], outputs, oracle, relay)
                finish_last_output(outputs, oracle)
                status = 'budget_exhausted' if oracle.ledger.exhausted else 'native_finished'
        except OracleBudgetExhausted:
            status, trace = 'budget_exhausted', {}
        except native.LongTruncation:
            try:
                finish_last_output(outputs, oracle)
                status = 'native_output_truncated'
            except OracleBudgetExhausted:
                status = 'budget_exhausted'
            trace = {}
        except Exception as error:
            native.dump(out/'error.json', {'type': type(error).__name__, 'error': str(error)[:300]})
            raise
        ledger = oracle.ledger
        if oracle.cursor != len(ledger.rows):
            raise RuntimeError('Oracle replay ended before the saved call sequence')
        metrics = ledger.metrics()
        source_counts = {}
        for row in ledger.rows:
            source = row['event_id'].split('/', 2)[-1]
            source_counts[source] = source_counts.get(source, 0)+1
        result = {'status': status, 'time': time.time(), **metrics, **relay.usage(),
                  'oracle_submissions': len(ledger.rows),
                  'physical_oracle_evaluations': len(ledger.buffer),
                  'oracle_query_sources': source_counts,
                  'model_outputs_after_initialization': len(outputs.rows),
                  'budget_exhausted': ledger.exhausted,
                  'auc_mt_mol_finish_true': mt_mol_auc(ledger.buffer, finish=True),
                  'initial_answer_reused_from_control': True,
                  'all_queries_in_auc': True}
        native.dump(out/'trace.json', trace)
        native.dump(out/'result.json', result)
        return result


def suite():
    RUNS.mkdir(exist_ok=True)
    with (RUNS/'suite.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        native.prepare_libraries()
        pilot = {method: job(method, 'qed') for method in ['chatdrug', 'agentdrug']}
        assert all(r['oracle_submissions'] <= 1000 for r in pilot.values())
        assert pilot['agentdrug']['oracle_submissions'] == 1000
        assert pilot['agentdrug']['oracle_query_sources'].get('reference_library') == 999
        assert pilot['agentdrug']['llm_calls'] == 0
        native.dump(RUNS/'pilot_validation.json', pilot)
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(job, method, task): (method, task)
                       for task in native.TASKS for method in ['chatdrug', 'agentdrug']}
            for future in concurrent.futures.as_completed(futures):
                print(json.dumps({'job': futures[future], 'result': future.result()}), flush=True)


if __name__ == '__main__':
    suite()
