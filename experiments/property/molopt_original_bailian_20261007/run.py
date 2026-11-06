"""Original 7100-case benchmark, with only the API provider switched to Bailian.

Task prompts, original online and final thresholds, chemistry preprocessing,
parsers, agent cores, and generation limits are inherited from frozen runners.
"""
import argparse
import ast
import collections
import concurrent.futures
import copy
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
BASE = Path('/data2/chenfuxin')
CHAT = BASE / 'chatdrug_generalization_20260920'
AGENT = BASE / 'agentdrug_20260922'
MODELS = ('ChatDrug', 'DeepSeek_direct', 'AgentDrug')
CATEGORY = {101: 'LogP', 102: 'LogP', 103: 'QED', 104: 'QED',
            105: 'TPSA', 106: 'TPSA', 107: 'HBA_HBD', 108: 'HBA_HBD',
            **{n: 'Dual' for n in range(201, 207)}}
PINS = {
    CHAT/'full_case.py': '76bbb86f1f9a299a77646611f273d32db319f69a17c4491f013801721830d45f',
    CHAT/'full_experiment.py': '0998f12f5f4da4910606d6c2aca85befe91103775c7b9f64793fea99dbf7375d',
    CHAT/'pilot.py': '0294a4125863744543545e9de6c7665646f17ba7442c1c4d6926fb856ba52331',
    CHAT/'deepseek_check.py': 'bc3de4735708ab814b38637aa038b503c7f56abc7745902785e9788fd71d18de',
    AGENT/'runner.py': '24aee817f4293dac507fcd66cadd5755aea290c48df968ba042d1d3a227b571c',
    AGENT/'core_fixed.py': '27ea4dba5b24106e8ad60f42826ef7d554d523385710fb41005aa282372dfb9d',
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def dependencies():
    for path, expected in PINS.items():
        assert sha(path) == expected, 'Frozen dependency changed: ' + str(path)
    sys.path.insert(0, str(CHAT))
    import full_experiment as benchmark
    from deepseek_check import config
    benchmark.p.env_config = config
    from provider import Relay
    benchmark.p.Relay = Relay
    return benchmark


def prepare():
    bench = dependencies()
    original = json.loads((CHAT/'prepared_full/cases.json').read_text())
    selected = copy.deepcopy(original)
    assert len(selected) == 7100 and len({c['id'] for c in selected}) == 7100
    assert collections.Counter(c['benchmark'] for c in selected) == {'ChatDrug': 5600, 'S2-mini': 1500}
    source_cases = [c for c in selected if c['benchmark'] == 'ChatDrug']
    target_cases = [c for c in selected if c['benchmark'] == 'S2-mini']
    assert len({c['smiles'] for c in source_cases}) == 200
    assert all('The output molecule should be similar to the input molecule.' in c['instruction'] for c in source_cases)
    assert collections.Counter((c['task'], c['constraint']) for c in source_cases) == {
        (task, setting): 200 for task in CATEGORY for setting in ('loose', 'strict')}
    assert collections.Counter(c['property'] for c in target_cases) == {'LogP': 500, 'QED': 500, 'MR': 500}
    assert not any((ROOT/'runs'/m).exists() for m in MODELS) or (ROOT/'cases.json').exists()
    cfg = {
        'created_utc': now(), 'expected_per_method': 7100, 'source_cases': 5600, 'target_cases': 1500,
        'methods': list(MODELS),
        'source_cases_sha256': sha(CHAT/'prepared_full/cases.json'),
        'retrieval_sha256': sha(CHAT/'prepared_full/retrieval.csv'),
        'frozen_dependencies': {str(p): h for p, h in PINS.items()},
        'model': 'deepseek-v4.1-flash', 'provider': 'Alibaba Bailian; user-requested original-protocol rerun',
        'temperature': 0, 'thinking': 'disabled', 'workers_per_lane': 2,
        'prompt_policy': 'All 7100 cases copied byte-for-byte from the original official-API experiment; no prompt edits.',
        'online_policy': 'Original ChatDrug and AgentDrug retrieval, feedback, thresholds, stopping, parsing, and generation caps retained.',
        'final_evaluation': 'Original full_experiment.score unchanged: ChatDrug loose/strict amplitude thresholds and Kekulize retained; original S2 LogP/QED/MR directional scoring retained.',
        'pairing': 'DeepSeek direct output shares ChatDrug initial response, as in the original experiment. Independent3 is omitted.',
        'caps': {'ChatDrug_and_direct': 2048, 'AgentDrug': 256},
        'pilot': '34 representative cases per method; successful pilot continues automatically to all 7100 using the same saved results.',
        'runtime_errors': 'Model-output failures remain in denominator. Network failures may be retried with stored-response replay; completed cases are never regenerated.',
        'provider_sha256': sha(ROOT/'provider.py'),
    }
    if (ROOT/'cases.json').exists():
        assert json.loads((ROOT/'cases.json').read_text()) == selected
    else:
        (ROOT/'cases.json').write_bytes((CHAT/'prepared_full/cases.json').read_bytes())
        dump(ROOT/'manifest.json', cfg)
    assert sha(ROOT/'cases.json') == sha(CHAT/'prepared_full/cases.json')
    source_tree = ast.parse((CHAT/'full_case.py').read_text())
    fn = next(n for n in source_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_case')
    run_try = next(n for n in fn.body if isinstance(n, ast.Try))
    start = next(i for i, n in enumerate(run_try.body) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'independent' for t in n.targets))
    end = next(i for i, n in enumerate(run_try.body) if ast.unparse(n) == "result['status'] = 'complete'")
    assert start < end
    # Only remove the unrequested independent-three arm after both wanted arms finish.
    run_try.body = run_try.body[:start] + run_try.body[end:]
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    generated = ast.unparse(module) + '\n'
    assert 'independent3' not in generated and 'shared_initial' in generated
    (ROOT/'pair_native.py').write_text(generated, encoding='utf-8')
    # Reproduce the saved original evaluator outcomes without making API calls.
    representatives = {}
    for c in selected:
        key = (c['benchmark'], c['task'] if c['benchmark']=='ChatDrug' else c['property'], c['constraint'], c['direction'])
        representatives.setdefault(key, c)
    assert len(representatives) == 34
    historical_checks = 0
    for case in representatives.values():
        native = json.loads((AGENT/'runs/full'/case['id']/'result.json').read_text())
        score = bench.score(case, native['candidate'])
        assert score == native['score'], case['id']
        assert not bench.score(case, None)['success']
        assert not bench.score(case, case['smiles'])['success']
        historical_checks += 1
    dump(ROOT/'validation.json', {'passed': True, 'cases_checked': 7100,
         'same_inputs_prompts_objectives_thresholds_and_ids': True, 'case_file_byte_identical': True,
         'original_evaluator_checks': historical_checks,
         'native_pair_change': 'Only independent3 postprocessing removed from frozen run_case.',
         'runner_sha256': sha(__file__), 'pair_native_sha256': sha(ROOT/'pair_native.py'),
         'rdkit_version': bench.p.rdkit.__version__})
    print(json.dumps({'prepared': len(selected), 'validation': 'passed'}), flush=True)


def finalize(bench, method, case, native, score, complete):
    path = ROOT/'runs'/method/case['id']/'result.json'
    if path.exists():
        return json.loads(path.read_text())
    candidate = score.get('candidate') if score else None
    final_score = bench.score(case, candidate)
    if not complete:
        final_score = bench.score(case, None)
    else:
        assert final_score == {k: v for k, v in score.items() if k in final_score}, case['id']
    result = {'id': case['id'], 'case': case, 'method': method,
              'status': 'complete' if complete else 'error', 'error': native.get('error') if not complete else None,
              'candidate': candidate, 'score_original_protocol': score,
              'score': final_score, 'native_seconds': native.get('seconds'),
              'response_models': native.get('response_models', []), 'finished_utc': now()}
    dump(path, result)
    return result


def pair_function(bench):
    p = bench.p
    p.score = bench.score
    p.retrieval_success = bench.retrieval_success
    ns = dict(p.__dict__)
    exec(compile((ROOT/'pair_native.py').read_text(), str(ROOT/'pair_native.py'), 'exec'), ns)
    return ns['run_case']


def agent_module():
    spec = importlib.util.spec_from_file_location('frozen_agentdrug_runner', AGENT/'runner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.init_corpus()
    return module


def run_pair(bench, native_fn, db, case):
    case_path = ROOT/'native/pair'/case['id']
    saved = case_path/'result.json'
    if saved.exists():
        native = json.loads(saved.read_text())
    else:
        native = native_fn(case, db, ROOT/'native/pair')
    for method, arm in [('ChatDrug', 'chatdrug'), ('DeepSeek_direct', 'direct')]:
        score = native.get('arms', {}).get(arm)
        # An agent-side error after the first response does not erase the direct output.
        complete = bool(score is not None and (arm == 'direct' or native.get('status') == 'complete'))
        finalize(bench, method, case, native, score, complete)
    return native


def run_agent(bench, agent, case):
    saved = ROOT/'native/agentdrug'/case['id']/'result.json'
    if saved.exists():
        native = json.loads(saved.read_text())
    else:
        out = saved.parent
        out.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        model = agent.Model(out)
        native = {'id': case['id'], 'case': case, 'status': 'running'}
        try:
            ns, args, batch, dataset = agent.setup(case)
            outputs, validity_work, iterations = ns['run_core'](args, batch, model, dataset)
            assert len(outputs) == 1
            candidate = outputs[0]['pred'][0]
            native.update(status='complete', candidate=candidate, score=bench.score(case, candidate),
                          generation_calls=len(model.predictions), validity_feedback_count=validity_work,
                          core_iterations=iterations, max_generations=args.refine_steps+1)
        except Exception as e:
            native.update(status='error', error=str(e) if isinstance(e, bench.p.RelayError) else type(e).__name__,
                          generation_calls=len(model.predictions))
        native.update(seconds=round(time.monotonic()-start, 3),
                      api_requests=sum(len(c.get('attempts', [])) for c in model.relay.calls),
                      response_models=sorted({c['response_model'] for c in model.relay.calls if c.get('response_model')}),
                      usage={k: sum(c.get('usage', {}).get(k, 0) or 0 for c in model.relay.calls)
                             for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens')})
        dump(saved, native)
    finalize(bench, 'AgentDrug', case, native, native.get('score'), native['status'] == 'complete')
    print(json.dumps({'case': case['id'], 'method': 'AgentDrug', 'status': native['status']}), flush=True)
    return native


def summary(lane):
    methods = MODELS[:2] if lane == 'pair' else MODELS[2:]
    cases = json.loads((ROOT/'cases.json').read_text())
    all_groups = []
    errors = []
    processed = {}
    for method in methods:
        groups = collections.defaultdict(collections.Counter)
        processed[method] = 0
        for case in cases:
            path = ROOT/'runs'/method/case['id']/'result.json'
            row = json.loads(path.read_text()) if path.exists() else None
            if row:
                processed[method] += 1
                if row['status'] == 'error':
                    errors.append({'method': method, 'id': case['id'], 'error': row.get('error')})
            dataset = 'ChatDrug' if case['benchmark'] == 'ChatDrug' else 'S2-mini'
            category = 'ChatDrug_'+CATEGORY[case['task']] if dataset == 'ChatDrug' else 'S2_'+case['property']
            detail = 'ChatDrug_'+str(case['task'])+'_'+case['constraint'] if dataset == 'ChatDrug' else 'S2_'+case['property']+'_'+case['direction']
            for label in ('Total', dataset, category, detail):
                g = groups[label]
                g['expected'] += 1
                g['processed'] += row is not None
                g['complete'] += bool(row and row['status'] == 'complete')
                g['success'] += bool(row and row['status'] == 'complete' and row['score']['success'])
        for label, g in groups.items():
            all_groups.append(dict(g, method=method, group=label,
                                   success_rate_full_denominator=g['success']/g['expected']))
    report = {'updated_utc': now(), 'lane': lane, 'processed': processed, 'groups': all_groups, 'errors': errors}
    dump(ROOT/('summary_'+lane+'.json'), report)
    return report


def verify_pilot(lane, cases):
    methods = MODELS[:2] if lane == 'pair' else MODELS[2:]
    failures = []
    for case in cases:
        for method in methods:
            row = json.loads((ROOT/'runs'/method/case['id']/'result.json').read_text())
            if row['status'] != 'complete':
                failures.append({'method': method, 'id': case['id'], 'error': row.get('error')})
        native_lane = 'pair' if lane == 'pair' else 'agentdrug'
        calls = json.loads((ROOT/'native'/native_lane/case['id']/'api_calls.json').read_text())
        first = next((c for c in calls if c.get('output')), None)
        if first is None:
            assert any(f['id'] == case['id'] for f in failures), 'Successful result has no saved response'
            continue
        user_text = '\n'.join(m['content'] for m in first['messages'] if m['role'] == 'user')
        assert case['instruction'] in user_text
        if case['benchmark'] == 'ChatDrug':
            assert 'The output molecule should be similar to the input molecule.' in user_text
        assert first['requested_model'] == 'deepseek-v4.1-flash'
    gate = {'passed': not failures, 'cases_per_method': len(cases), 'methods': methods,
            'prompt_checked_in_real_requests': True, 'failures': failures, 'updated_utc': now()}
    dump(ROOT/('pilot_gate_'+lane+'.json'), gate)
    assert gate['passed'], 'Pilot has runtime failures; inspect preserved diagnostics before continuing.'


def run(lane, workers):
    bench = dependencies()
    validation = json.loads((ROOT/'validation.json').read_text())
    assert validation['runner_sha256'] == sha(__file__)
    assert validation['pair_native_sha256'] == sha(ROOT/'pair_native.py')
    lock = (ROOT/(lane+'.lock')).open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cases = json.loads((ROOT/'cases.json').read_text())
    assert len(cases) == 7100
    # Interleave original 28 source settings and six S2 property/direction settings.
    buckets = collections.defaultdict(list)
    for c in cases:
        buckets[(c['benchmark'], c['task'] if c['benchmark']=='ChatDrug' else c['property'], c['constraint'], c['direction'])].append(c)
    assert len(buckets) == 34
    ordered = [items[i] for i in range(max(map(len, buckets.values()))) for items in buckets.values() if i < len(items)]
    assert len(ordered) == 7100
    pilot = ordered[:34]
    if lane == 'pair':
        native_fn = pair_function(bench)
        db = bench.p.pd.read_csv(CHAT/'prepared_full/retrieval.csv')
        case_fn = lambda c: run_pair(bench, native_fn, db, c)
    else:
        agent = agent_module()
        case_fn = lambda c: run_agent(bench, agent, c)
    consecutive_infrastructure = 0
    try:
        for phase, selected in [('pilot', pilot), ('full', ordered[34:])]:
            dump(ROOT/('state_'+lane+'.json'), {'state': phase+'_running', 'pid': os.getpid(), 'updated_utc': now()})
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                methods = MODELS[:2] if lane=='pair' else MODELS[2:]
                pending_cases = [c for c in selected if not all((ROOT/'runs'/m/c['id']/'result.json').exists() for m in methods)]
                iterator = iter(pending_cases)
                pending = {}
                for _ in range(workers):
                    c = next(iterator, None)
                    if c:
                        pending[pool.submit(case_fn, c)] = c
                completed = 0
                while pending:
                    ready, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in ready:
                        native = future.result()
                        del pending[future]
                        completed += 1
                        error = native.get('error', '') or ''
                        infrastructure = native.get('status') == 'error' and (
                            error.startswith('HTTP_') or error in ['TRANSPORT_ERROR', 'NO_TEXT_BLOCK', 'INVALID_JSON', 'RETRY_EXHAUSTED'])
                        consecutive_infrastructure = consecutive_infrastructure+1 if infrastructure else 0
                        if consecutive_infrastructure >= 3:
                            raise RuntimeError('CONSECUTIVE_INFRASTRUCTURE_ERRORS')
                        if completed % 10 == 0 or phase == 'pilot':
                            summary(lane)
                        c = next(iterator, None)
                        if c:
                            pending[pool.submit(case_fn, c)] = c
            summary(lane)
            if phase == 'pilot':
                verify_pilot(lane, pilot)
        report = summary(lane)
        assert all(n == 7100 for n in report['processed'].values())
        dump(ROOT/('state_'+lane+'.json'), {'state': 'finished', 'errors': len(report['errors']),
             'pid': os.getpid(), 'updated_utc': now()})
    except Exception as e:
        summary(lane)
        dump(ROOT/('state_'+lane+'.json'), {'state': 'halted', 'reason': str(e),
             'pid': os.getpid(), 'updated_utc': now()})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'run', 'summary'])
    parser.add_argument('--lane', choices=['pair', 'agentdrug'])
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare()
    else:
        assert args.lane
        if args.command == 'run':
            run(args.lane, args.workers)
        else:
            print(json.dumps(summary(args.lane)), flush=True)
