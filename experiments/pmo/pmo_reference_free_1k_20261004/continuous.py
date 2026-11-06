"""Repeat native editor episodes until 1,000 counted oracle submissions."""
import argparse
import ast
import collections
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parent
PREVIOUS = Path('/data2/chenfuxin/pmo_reference_free_20261004')
sys.path.insert(0, str(PREVIOUS))
import run_free as base
n = base.native
old = base.old
METHODS = base.METHODS


def verify():
    base.verify()
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for path, digest in manifest['frozen_inputs'].items():
        if n.sha(path) != digest:
            raise RuntimeError('Continuous-run frozen input changed: '+path)
    return manifest


class CachedMorgan:
    """Cache the identical immutable RDKit fingerprint, never change similarity."""
    def __init__(self):
        self.objects = {}
    def GetMorganFingerprint(self, mol, radius):
        key = (id(mol), radius)
        if key not in self.objects:
            self.objects[key] = (mol, n.AllChem.GetMorganFingerprint(mol, radius))
        return self.objects[key][1]


def editor(method, fingerprints):
    source = (PREVIOUS/'snapshot/run_editors.py').read_text()
    tree = ast.parse(source)
    node = next(t for t in tree.body if isinstance(t, ast.FunctionDef) and t.name == method)
    text = ast.get_source_segment(source, node)
    if method == 'agentdrug':
        original = "    db = pd.read_csv(ROOT/'native_data/agentdrug_10000.csv')\n    db['mol'] = db['SMILES'].apply(Chem.MolFromSmiles)\n    db['prop'] = db['SMILES'].apply(lambda sm: scores.get(sm, 'reference_library'))"
    else:
        original = "    db = pd.read_csv(ROOT/'native_data/chatdrug_10000.csv')"
    assert text.count(original) == 1
    text = text.replace(original, '    db = scores.reference_db.copy(deep=True)')
    if method == 'chatdrug':
        original_similarity = '''        return DataStructs.TanimotoSimilarity(
            AllChem.GetMorganFingerprint(Chem.MolFromSmiles(a), 2),
            AllChem.GetMorganFingerprint(Chem.MolFromSmiles(b), 2))'''
        assert text.count(original_similarity) == 1
        text = text.replace(original_similarity,
                            '        return DataStructs.TanimotoSimilarity(scores.fingerprint(a), scores.fingerprint(b))')
    namespace = dict(n.__dict__)
    namespace['AllChem'] = fingerprints
    exec(compile(text, 'native_editor_prepared_reference_db', 'exec'), namespace)
    return namespace[method]


class Oracle(old.UnifiedOracle):
    def __init__(self, out, evaluator, method, task, budget):
        super().__init__(out, evaluator, budget)
        self.method, self.task, self.evaluator = method, task, evaluator
        path, raw = base.library(method)
        column = 'SMILES' if method == 'agentdrug' else 'sequence'
        self.reference_db = n.pd.DataFrame({column: raw})
        self.raw_canonical = {}
        self.reference_index = {}
        for i, sm in enumerate(raw):
            # Native ChatDrug removes embedded newlines before reference evaluation.
            # Preserve the original DB verbatim and accept that exact loader cleanup.
            for lookup in (sm, sm.replace('\n', '')):
                self.raw_canonical[lookup] = n.canonical(sm)
                self.reference_index[lookup] = i
        self.reference_cache_sha = None
        self.fingerprints = {}
        if method == 'agentdrug':
            payload = base.reference_payload(task)
            self.free_cache = payload['scores']
            self.reference_cache_sha = n.sha(base.REFERENCES/task/'scores.json')
            self.reference_db['mol'] = self.reference_db['SMILES'].apply(n.Chem.MolFromSmiles)
            self.reference_db['prop'] = [self.free_cache[self.raw_canonical[sm]] for sm in raw]
            n.dump(out/'reference_preparation.json', {
                'entries': 10000, 'library_sha': n.sha(path),
                'score_cache_sha': self.reference_cache_sha,
                'offline_scores_reused': True, 'online_reference_evaluations': 0})
        else:
            self.free_cache = {}
            journal = out/'reference_evaluations.jsonl'
            if journal.exists():
                for line in journal.read_text().splitlines():
                    row = json.loads(line)
                    self.free_cache[row['smiles']] = row['score']
        self.begin_episode()

    def begin_episode(self):
        self.free_ids = []

    def fingerprint(self, smiles):
        if smiles not in self.fingerprints:
            self.fingerprints[smiles] = n.AllChem.GetMorganFingerprint(n.Chem.MolFromSmiles(smiles), 2)
        return self.fingerprints[smiles]

    def get(self, smiles, source):
        free = ((self.method == 'chatdrug' and source == 'retrieval_feedback') or
                (self.method == 'agentdrug' and source == 'reference_library'))
        if not free:
            return super().get(smiles, source)
        if smiles not in self.raw_canonical:
            raise RuntimeError('Reference query is not from the frozen 10,000-row library')
        sm = self.raw_canonical[smiles]
        if sm not in self.free_cache:
            if self.method == 'agentdrug':
                raise RuntimeError('Missing precomputed reference score')
            value = float(self.evaluator(sm))
            if not base.math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid reference score')
            n.append(self.out/'reference_evaluations.jsonl', {'smiles': sm, 'score': value})
            self.free_cache[sm] = value
        self.free_ids.append(self.reference_index[smiles])
        return self.free_cache[sm]


class Outputs:
    def __init__(self, out, oracle):
        self.out, self.oracle, self.rows = out, oracle, []
    def submit(self, smiles, event_id):
        row = {'event_id': event_id, 'raw': smiles,
               'oracle_cursor_at_generation': self.oracle.cursor}
        self.rows.append(row)
        n.dump(self.out/'model_outputs.json', self.rows)
        return row


class EpisodeRelay:
    def __init__(self, inner, oracle, episode):
        self.inner, self.oracle, self.episode = inner, oracle, episode
    def complete(self, messages, label, cap=None):
        if self.oracle.cursor >= self.oracle.ledger.budget:
            raise old.OracleBudgetExhausted()
        return self.inner.complete(messages, f'episode/{self.episode}/{label}', cap=cap)


def choose_parent(parent, outputs, ledger):
    """Carry the best generated answer forward; free reference scores cannot win."""
    best = n.canonical(parent)
    best_score = ledger.buffer[best][0]
    for row in outputs.rows:
        sm = n.canonical(row['raw'])
        if sm in ledger.buffer and ledger.buffer[sm][0] > best_score:
            best, best_score = sm, ledger.buffer[sm][0]
    return best


def final_result(out, oracle, relay, state, status):
    ledger = oracle.ledger
    if status == 'complete':
        assert len(ledger.rows) == ledger.budget and oracle.cursor == ledger.budget
    counts = dict(collections.Counter(r['event_id'].split('/', 2)[-1] for r in ledger.rows))
    assert not {'reference_library', 'retrieval_feedback'}.intersection(counts)
    episodes = [json.loads(p.read_text()) for p in (out/'episodes').glob('*/episode.json')]
    ranked = sorted((v[0] for v in ledger.buffer.values()), reverse=True)
    result = {
        'status': status, 'time': time.time(), **ledger.metrics(), **relay.usage(),
        'oracle_submissions': len(ledger.rows), 'oracle_query_sources': counts,
        'episodes': len(episodes),
        'model_outputs_after_initialization': sum(e['model_outputs'] for e in episodes),
        'reference_scores_in_auc': False,
        'reference_cache_sha': oracle.reference_cache_sha,
        'free_retrieval_queries': sum(e['free_reference_queries'] for e in episodes),
        'agentdrug_precomputed_reference_entries': 10000 if oracle.method == 'agentdrug' else 0,
        'budget_exhausted': ledger.exhausted,
        'auc_is_tail_filled': status != 'complete',
        'early_stop_reason': None if status == 'complete' else status,
        'auc_top10': base.mt_mol_auc(ledger.buffer, ledger.budget, finish=True),
        'auc_observed_only': base.mt_mol_auc(ledger.buffer, ledger.budget, finish=ledger.exhausted),
        'top1': ranked[0] if ranked else 0.0,
        'top10': sum(ranked[:10])/len(ranked[:10]) if ranked else 0.0}
    n.dump(out/'result.json', result)
    n.dump(out/'progress.json', result)
    return result


def job(method, task, stage='full', budget=1000, quantum=10):
    manifest = verify()
    os.chdir(n.LEGACY)
    out = ROOT/('runs' if stage == 'full' else 'pilot')/method/task/'0'
    out.mkdir(parents=True, exist_ok=True)
    with (out/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'result.json').exists():
            return json.loads((out/'result.json').read_text())
        seed = json.loads((PREVIOUS/'initial_answers.json').read_text())[task]
        config = {
            'method': method, 'task': task, 'seed': 0, 'stage': stage,
            'oracle_query_budget': budget, 'model': n.run_direct.MODEL,
            'initial_answer': seed['raw'], 'initialization_counts_once': True,
            'repeat_native_episodes_until_budget': True, 'stop_on_success': False,
            'parent_policy': 'best valid generated candidate so far; never free references',
            'duplicate_queries_consume_budget': True,
            'reference_queries_count': False, 'feedback_queries_count': True,
            'reference_scores_in_auc': False,
            'library_sha': n.sha(base.library(method)[0]),
            'native_editor_round_limits_unchanged': True,
            'scheduling_quantum_episodes': quantum,
            'source_hashes': manifest['frozen_inputs']}
        if (out/'config.json').exists():
            assert json.loads((out/'config.json').read_text()) == config
        n.dump(out/'config.json', config)
        oracle = Oracle(out, n.make_oracle(n.TASKS[task][0]), method, task, budget)
        relay = n.Relay(out)
        state_path = out/'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            oracle.cursor = state['boundary']
        else:
            oracle.get(seed['raw'], 'initial_model_answer')
            state = {'episode': 0, 'parent': n.canonical(seed['raw']), 'boundary': 1}
            n.dump(state_path, state)
        if state['parent'] is None:
            return final_result(out, oracle, relay, state, 'invalid_initial_answer')
        native_editor = editor(method, CachedMorgan())
        first_episode = state['episode']
        try:
            while oracle.cursor < budget:
                if len(relay.long_truncations) >= 3:
                    # Original provider-truncation policy, independent of edit success.
                    return final_result(out, oracle, relay, state, 'skipped_provider_truncation')
                if state['episode']-first_episode >= quantum:
                    n.dump(out/'progress.json', {
                        'status': 'queued', 'time': time.time(), **oracle.ledger.metrics(),
                        'episodes': state['episode'], 'model_usage': relay.usage()})
                    return {'status': 'yielded'}
                episode = state['episode']
                episode_out = out/'episodes'/f'{episode:06d}'
                episode_out.mkdir(parents=True, exist_ok=True)
                oracle.begin_episode()
                outputs = Outputs(episode_out, oracle)
                n.dump(out/'progress.json', {
                    'status': 'running', 'time': time.time(), **oracle.ledger.metrics(),
                    'episode': episode, 'parent': state['parent']})
                try:
                    trace = native_editor(task, state['parent'], outputs, oracle,
                                          EpisodeRelay(relay, oracle, episode))
                    old.finish_last_output(outputs, oracle)
                except old.OracleBudgetExhausted:
                    trace = {'budget_exhausted': True}
                except n.LongTruncation:
                    trace = {'provider_truncation': True}
                    try:
                        old.finish_last_output(outputs, oracle)
                    except old.OracleBudgetExhausted:
                        pass
                if oracle.cursor <= state['boundary']:
                    raise RuntimeError('Native episode made no real oracle submission')
                parent = choose_parent(state['parent'], outputs, oracle.ledger)
                n.dump(episode_out/'episode.json', {
                    'episode': episode, 'parent': state['parent'], 'next_parent': parent,
                    'before': state['boundary'], 'after': oracle.cursor,
                    'model_outputs': len(outputs.rows),
                    'free_reference_queries': len(oracle.free_ids),
                    'reference_indices_in_query_order': oracle.free_ids,
                    'trace': trace})
                state = {'episode': episode+1, 'parent': parent, 'boundary': oracle.cursor}
                n.dump(state_path, state)
            return final_result(out, oracle, relay, state, 'complete')
        except Exception as error:
            n.dump(out/'error.json', {
                'time': time.time(), 'type': type(error).__name__, 'error': str(error)[:300],
                'episode': state['episode'], 'oracle_submissions': len(oracle.ledger.rows),
                'result_is_complete': False})
            raise


def status():
    rows = []
    for out in (ROOT/'runs').glob('*/*/0'):
        method, task = out.parent.parent.name, out.parent.name
        path = out/'result.json' if (out/'result.json').exists() else out/'progress.json'
        value = json.loads(path.read_text()) if path.exists() else {'status': 'starting'}
        ledger_path = out/'oracle_queries.jsonl'
        counted = len(ledger_path.read_text().splitlines()) if ledger_path.exists() else 0
        rows.append({'method': method, 'task': task, **value, 'actual_oracle_submissions': counted})
    summary = {
        'time': time.time(), 'expected_jobs': 46, 'started_jobs': len(rows),
        'states': dict(collections.Counter(r['status'] for r in rows)),
        'actual_oracle_submissions': sum(r['actual_oracle_submissions'] for r in rows),
        'jobs': rows}
    n.dump(ROOT/'summary.json', summary)
    return summary


def audit_and_report():
    verify()
    results = []
    for method in METHODS:
        for task in n.TASKS:
            out = ROOT/'runs'/method/task/'0'
            r = json.loads((out/'result.json').read_text())
            ledger = base.SubmissionLedger(out/'oracle_queries.jsonl', n.canonical, lambda sm: 0)
            assert len(ledger.rows) == r['oracle_submissions'] <= 1000
            if r['status'] == 'complete':
                assert len(ledger.rows) == 1000 and not r['auc_is_tail_filled']
            else:
                assert r['early_stop_reason'] and r['auc_is_tail_filled']
            assert not any(row['event_id'].endswith(('/reference_library', '/retrieval_feedback')) for row in ledger.rows)
            assert abs(base.mt_mol_auc(ledger.buffer, finish=True)-r['auc_top10']) < 1e-12
            initial_count = sum(row['event_id'].endswith('/initial_model_answer') for row in ledger.rows)
            assert initial_count == 1
            results.append({'method': method, 'task': task, **r})
    aggregate = {}
    for method in METHODS:
        group = [r for r in results if r['method'] == method]
        aggregate[method] = {
            'tasks': len(group), 'complete_1000': sum(r['status'] == 'complete' for r in group),
            'oracle_submissions': sum(r['oracle_submissions'] for r in group),
            'sum_auc_top10': sum(r['auc_top10'] for r in group),
            'early_stops': [{'task': r['task'], 'reason': r['early_stop_reason'], 'queries': r['oracle_submissions']}
                            for r in group if r['status'] != 'complete']}
    n.dump(ROOT/'final_validation.json', {'passed': True, 'jobs': 46, 'summary': aggregate})
    lines = ['# PMO-1K 连续提交：参考库不计预算', '',
             '达到更高分继续运行；complete 表示真实提交 1,000 次。参考库不纳入 AUC。', '',
             '| 方法 | 满 1000 次的任务 | 计费查询合计 | Top-10 AUC 合计 |',
             '|---|---:|---:|---:|']
    for method, r in aggregate.items():
        lines.append(f"| {method} | {r['complete_1000']}/23 | {r['oracle_submissions']} | {r['sum_auc_top10']:.6f} |")
    lines += ['', '| 方法 | 任务 | 实际查询 | 状态 | AUC | 是否补尾 |', '|---|---|---:|---|---:|---|']
    for r in results:
        lines.append(f"| {r['method']} | {r['task']} | {r['oracle_submissions']} | {r['status']} | {r['auc_top10']:.6f} | {r['auc_is_tail_filled']} |")
    (ROOT/'RESULTS.md').write_text('\n'.join(lines)+'\n')


def suite(workers=4, quantum=10):
    (ROOT/'runs').mkdir(exist_ok=True)
    with (ROOT/'suite.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pending = collections.deque((m, t) for t in n.TASKS for m in METHODS)
        retries = collections.Counter()
        failures = []
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            active = {}
            while pending or active:
                while pending and len(active) < workers:
                    method, task = pending.popleft()
                    active[pool.submit(job, method, task, 'full', 1000, quantum)] = (method, task)
                done, _ = concurrent.futures.wait(active, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    spec = active.pop(future)
                    try:
                        result = future.result()
                        if result['status'] == 'yielded':
                            pending.append(spec)
                        print(json.dumps({'job': spec, 'status': result['status'],
                                          'queries': result.get('oracle_submissions')}), flush=True)
                    except Exception as error:
                        retries[spec] += 1
                        if retries[spec] <= 3:
                            pending.append(spec)
                        else:
                            failures.append({'job': spec, 'error': str(error)[:300]})
                        print(json.dumps({'job': spec, 'retry': retries[spec], 'error_type': type(error).__name__}), flush=True)
                    status()
        n.dump(ROOT/'suite_failures.json', failures)
        summary = status()
        if failures or sum(summary['states'].get(s, 0) for s in ('complete', 'invalid_initial_answer', 'skipped_provider_truncation')) != 46:
            raise RuntimeError('Some tasks remain incomplete; see suite_failures.json')
        audit_and_report()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['suite', 'job', 'status'])
    parser.add_argument('--method', choices=METHODS)
    parser.add_argument('--task', choices=list(n.TASKS), default='qed')
    parser.add_argument('--stage', choices=['full', 'pilot'], default='full')
    parser.add_argument('--budget', type=int, default=1000)
    parser.add_argument('--quantum', type=int, default=10)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    verify()
    if args.action == 'suite':
        suite(args.workers, args.quantum)
    elif args.action == 'job':
        value = job(args.method, args.task, args.stage, args.budget, args.quantum)
        print(json.dumps(value), flush=True)
        if value['status'] == 'yielded':
            raise SystemExit(75)
    else:
        value = status()
        print(json.dumps({k: v for k, v in value.items() if k != 'jobs'}), flush=True)
