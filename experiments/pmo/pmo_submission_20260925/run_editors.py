"""One model-generated start, followed by each editor's own bounded workflow.

No cross-episode search, parent selection, history, or iteration to fill budget.
"""
import ast
import concurrent.futures
import fcntl
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import types

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent
LEGACY = Path('/data2/chenfuxin/pmo_1k_20260924')
sys.path.insert(0, str(LEGACY))
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem
from pmo_common import Relay, LongTruncation, canonical, make_oracle, dump, sha, functions
from task_specs import TASKS
from submission_budget import SubmissionLedger, mt_mol_auc
import run_direct

CHAT = Path('/data2/chenfuxin/chatdrug_generalization_20260920')
AGENT = Path('/data2/chenfuxin/agentdrug_20260922')


def append(path, row):
    with path.open('a') as handle:
        handle.write(json.dumps(row)+'\n')
        handle.flush()
        os.fsync(handle.fileno())


class Scores:
    """Keep internal/retrieval oracle use separate from submitted answers."""
    def __init__(self, out, evaluator):
        self.out, self.evaluator, self.cache = out, evaluator, {}
        path = out/'oracle_evaluations.jsonl'
        if path.exists():
            for line in path.read_text().splitlines():
                row = json.loads(line)
                self.cache[row['smiles']] = row['score']

    def get(self, sm, source):
        sm = canonical(sm)
        if sm is None:
            return 0.0
        cached = sm in self.cache
        if not cached:
            start = time.time()
            score = float(self.evaluator(sm))
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Nonfinite or out-of-range oracle score')
            append(self.out/'oracle_evaluations.jsonl',
                   {'smiles': sm, 'score': score, 'source': source,
                    'seconds': time.time()-start})
            self.cache[sm] = score
        append(self.out/'oracle_access.jsonl', {'smiles': sm, 'source': source, 'cached': cached})
        return self.cache[sm]


def initial_row(task):
    folder = ROOT/'runs/deepseek'/task/'0'
    path = folder/'answers.jsonl'
    started = time.monotonic()
    while not path.exists() or not path.stat().st_size:
        # Produce the control's first answer using its exact existing runner.
        # A running control owns its lock; callers can retry without another API call.
        try:
            run_direct.job(task, smoke_limit=1)
        except BlockingIOError:
            if time.monotonic()-started > 300:
                raise TimeoutError('Control initialization is still pending')
            time.sleep(1)
    with path.open() as handle:
        row = json.loads(handle.readline())
    assert row['index'] == 1
    return row, path


def prepare_libraries():
    folder = ROOT/'native_data'
    folder.mkdir(exist_ok=True)
    # ChatDrug author's loader: remove its source inputs, sample 10K at seed 0.
    source = CHAT/'data/ChatDrug_data/small_molecule/250k_rndm_zinc_drugs_clean_3.csv'
    inputs = source.parent/'small_molecule_editing.txt'
    if not (folder/'chatdrug_10000.csv').exists():
        db = pd.read_csv(source)[['smiles']].rename(columns={'smiles': 'sequence'})
        for sm in set(inputs.read_text().splitlines()):
            db = db[db['sequence'].str.find(sm) < 0]
        db.sample(10000, random_state=0).to_csv(folder/'chatdrug_10000.csv', index=False)
    # AgentDrug GenerationDataset shuffles at 42 then takes DB_size=10K.
    source_agent = folder/'agentdrug_database.csv'
    if not (folder/'agentdrug_10000.csv').exists():
        db = pd.read_csv(source_agent).sample(frac=1, random_state=42).reset_index(drop=True).head(10000)
        db['SMILES'] = db['SMILES'].str.replace('\\\\', '\\', regex=False)
        db[['SMILES']].to_csv(folder/'agentdrug_10000.csv', index=False)
    dump(folder/'sampling_manifest.json', {
        'chatdrug_source': str(source), 'chatdrug_source_sha': sha(source),
        'chatdrug_sample_sha': sha(folder/'chatdrug_10000.csv'),
        'agentdrug_source_sha': sha(source_agent),
        'agentdrug_sample_sha': sha(folder/'agentdrug_10000.csv'),
        'source_input_molecules_used_as_initialization': False})


def editing_prompt(task, parent):
    return (f'PMO molecular optimization objective: {task}. {TASKS[task][1]} '
            'Scores range from 0 to 1; higher is better. '
            f'Improve the following starting molecule for this objective: {parent}')


def chatdrug(task, parent, ledger, scores, relay):
    upstream = CHAT/'upstream/ChatDrug'
    parser = functions(upstream/'ChatDrug/task_and_evaluation/small_molecule_editing.py',
                       ['parse_molecule'], {'re': re})['parse_molecule']
    base = scores.get(parent, 'parent_feedback')
    db = pd.read_csv(ROOT/'native_data/chatdrug_10000.csv')
    count = 0
    def complete(messages, *args):
        nonlocal count
        count += 1
        try:
            return relay.complete(messages, f'chatdrug/{count}')
        except LongTruncation:
            ledger.submit(None, f'chatdrug/{count}')
            raise
    def parse(task_id, inp, text, closest):
        candidates = parser(inp, text, closest)
        # trial_index=0 is the author's tested output. No scoring hidden extras.
        ledger.submit(candidates[0] if candidates else None, f'chatdrug/{count}')
        return candidates
    def evaluate(inp, candidate, *args, **kwargs):
        if canonical(candidate) is None:
            return -1
        return scores.get(candidate, 'candidate_feedback') > base
    def retrieval_evaluate(inp, candidate, *args, **kwargs):
        return scores.get(candidate, 'retrieval_feedback') > base
    def similarity(task_id, a, b):
        return DataStructs.TanimotoSimilarity(
            AllChem.GetMorganFingerprint(Chem.MolFromSmiles(a), 2),
            AllChem.GetMorganFingerprint(Chem.MolFromSmiles(b), 2))
    retrieval = functions(upstream/'utils.py', ['retrieve_and_feedback'],
                          {'sim_sequence': similarity, 'evaluate': retrieval_evaluate})
    ns = {'sys': sys, 'complete': complete, 'parse': parse, 'evaluate': evaluate,
          'retrieve_and_feedback': retrieval['retrieve_and_feedback']}
    functions(upstream/'main_ChatDrug.py', ['conversation', 'ReDF'], ns)
    record = {parent: {'retrieval_conversation': [{'result': i} for i in range(3)],
                       'skip_conversation_round': -1}}
    messages = [{'role': 'system', 'content': 'You are an expert in the field of molecular chemistry.'},
                {'role': 'user', 'content': editing_prompt(task, parent)+
                 ' Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.'}]
    log = io.StringIO()
    for i in range(3):
        answer, candidate = ns['conversation'](messages, None, None, 'chatgpt', 2, i, 0, 101,
            'molecule', parent, db, record, log, False, 'loose', {}, None, None)
        if answer != 0 or candidate is None:
            break
    return {'record': record, 'log': log.getvalue()}


def agentdrug(task, parent, ledger, scores, relay):
    code = (AGENT/'core_fixed.py').read_text()
    anchor = '                        if prop == "LogP+":'
    assert code.count(anchor) == 1
    code = code.replace(anchor, '''                        if prop == "PMO+":
                            hit = output_prop > input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop]
                            property_feedback = f"The modified molecule has a PMO objective score of {output_prop:.6f} and the original one has {input_prop:.6f}. A higher score is desired."
'''+anchor)
    ns = {'Chem': Chem, 'AllChem': AllChem, 'DataStructs': DataStructs,
          'task2func': {'PMO+': lambda mol: scores.get(Chem.MolToSmiles(mol), 'candidate_feedback')},
          'task2thres': {'PMO+': [[0], [0]]},
          'get_validity_feedback': lambda sm, _: 'The modified molecule is chemically valid.'
              if canonical(sm) else 'The modified molecule is not chemically valid.',
          'listize_fn': lambda batch: {k: [v] for k, v in batch.items()}}
    exec(compile(code, 'agentdrug_pmo_native_core', 'exec'), ns)
    db = pd.read_csv(ROOT/'native_data/agentdrug_10000.csv')
    db['mol'] = db['SMILES'].apply(Chem.MolFromSmiles)
    db['prop'] = db['SMILES'].apply(lambda sm: scores.get(sm, 'reference_library'))
    class Model:
        def __init__(self):
            self.n = 0
        def inference(self, batch):
            self.n += 1
            try:
                text = relay.complete([{'role': 'user', 'content': batch['prompt'][0]}],
                                      f'agentdrug/{self.n}', cap=256)
            except LongTruncation:
                ledger.submit(None, f'agentdrug/{self.n}')
                raise
            cleaned = text.strip().split('->', 1)[-1].split('becomes', 1)[-1].strip()
            ledger.submit(cleaned, f'agentdrug/{self.n}')
            return {'id': batch['id'], 'label': batch['smiles'], 'pred': [text.strip()]}
    batch = {'id': task, 'smiles': parent, 'label': None,
             'prompt': editing_prompt(task, parent)+
             '\nRespond with only the SMILES string of your modified molecule. No explanation is needed.'+
             '\n\nMolecule:'+parent+'\nAnswer:'}
    outputs, valid, total = ns['run_core'](
        types.SimpleNamespace(data='single/PMO+', refine_steps=3, hit_thres=0),
        batch, Model(), types.SimpleNamespace(DB=db))
    return {'outputs': outputs, 'validity_feedback': valid, 'iterations': total}


def job(method, task):
    os.chdir(LEGACY)
    for path, digest in json.loads((LEGACY/'prepared/dependencies.json').read_text()).items():
        if sha(path) != digest:
            raise RuntimeError('Verified oracle dependency changed: '+path)
    out = ROOT/'runs'/method/task/'0'
    out.mkdir(parents=True, exist_ok=True)
    with (out/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'result.json').exists():
            return json.loads((out/'result.json').read_text())
        seed, source = initial_row(task)
        library = ROOT/f'native_data/{method}_10000.csv'
        config = {'method': method, 'task': task, 'model': run_direct.MODEL,
                  'budget': 1000, 'initial_source': str(source),
                  'initial_event': seed['event_id'], 'initial_answer': seed['raw'],
                  'initial_policy': 'same first model answer as control, counts as submission',
                  'workflow': 'one native editing episode; stop naturally',
                  'cross_episode_history': False, 'search_outer_loop': False,
                  'library_sha': sha(library), 'code_sha': sha(Path(__file__)),
                  'core_sha': sha(AGENT/'core_fixed.py') if method == 'agentdrug' else
                              sha(CHAT/'upstream/ChatDrug/main_ChatDrug.py')}
        if (out/'config.json').exists():
            assert json.loads((out/'config.json').read_text()) == config
        dump(out/'config.json', config)
        scores = Scores(out, make_oracle(TASKS[task][0]))
        ledger = SubmissionLedger(out/'answers.jsonl', canonical,
                                  lambda sm: scores.get(sm, 'submitted_answer'))
        ledger.submit(seed['raw'], 'initial/model')
        relay = Relay(out)
        dump(out/'progress.json', {'status': 'running_native_episode', 'time': time.time()})
        try:
            if canonical(seed['raw']) is None:
                status, trace = 'invalid_initial_answer', {}
            else:
                trace = {'chatdrug': chatdrug, 'agentdrug': agentdrug}[method](
                    task, seed['raw'], ledger, scores, relay)
                status = 'native_finished'
        except LongTruncation:
            status, trace = 'native_output_truncated', {}
        dump(out/'trace.json', trace)
        metrics = ledger.metrics()
        # Natural termination is not budget exhaustion. Report both AUC conventions.
        result = {'status': status, 'time': time.time(), **metrics, **relay.usage(),
                  'oracle_unique_evaluations_including_references': len(scores.cache),
                  'auc_observed_only': metrics['auc_top10_mt_mol'],
                  'auc_mt_mol_finish_true': mt_mol_auc(ledger.buffer, finish=True),
                  'budget_exhausted': ledger.exhausted,
                  'initial_llm_answer_reused_from_control': True}
        dump(out/'result.json', result)
        return result


def suite():
    with (ROOT/'editors_suite.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare_libraries()
        pilot = {method: job(method, 'qed') for method in ['chatdrug', 'agentdrug']}
        for method, result in pilot.items():
            assert result['status'] == 'native_finished' and result['submissions'] >= 2, (method, result)
        dump(ROOT/'editors_pilot_validation.json', pilot)
        # Independent native executions; no task-level optimizer or feedback sharing.
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(job, method, task): (method, task)
                       for task in TASKS for method in ['chatdrug', 'agentdrug']}
            for future in concurrent.futures.as_completed(futures):
                print(json.dumps({'job': futures[future], 'result': future.result()}), flush=True)


if __name__ == '__main__':
    suite()
