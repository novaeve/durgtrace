"""Forensic audit only: do not modify submissions, scores or rerun cases."""
from pathlib import Path
import collections
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for path, digest in manifest['baseline_files'].items():
        assert sha(Path(path)) == digest
    for path, digest in manifest['source_hashes'].items():
        assert sha(ROOT / path) == digest
    paths = sorted((ROOT / 'runs/full').glob('*/result.json'))
    assert len(paths) == 3800
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    score = ROOT / 'runs/full/scores.json'
    score_hash = sha(score)
    reports, unresolved = [], []
    for path in paths:
        row = json.loads(path.read_text())
        if row['status'] == 'complete':
            continue
        records = []
        truncated, errors, pending = [], [], []
        for api in sorted((path.parent / 'api').glob('*.json')):
            record = json.loads(api.read_text())
            actual = record['settings']
            assert actual['model'] == 'deepseek-v4.1-flash' and actual['temperature'] == 0
            assert actual['enable_thinking'] is False and actual['max_tokens'] is None
            assert actual['reasoning_effort'] is None
            records.append(record)
            response = record.get('response') or {}
            choices = response.get('choices') or []
            if choices and choices[0].get('finish_reason') == 'length':
                truncated.append({'file': api.name, 'http_status': record.get('http_status'),
                                  'finish_reason': 'length',
                                  'output_tokens': response.get('usage', {}).get('completion_tokens')})
            if record.get('error') and 'truncated' not in record['error']:
                errors.append({'file': api.name, 'http_status': record.get('http_status'),
                               'error': record['error']})
            if not record.get('ended'):
                pending.append(api.name)
        report = {'id': row['id'], 'bench': row['bench'], 'status': row['status'],
                  'seconds': row.get('seconds'), 'model_requests': len(records),
                  'api_errors': errors, 'unfinished_api_calls': pending,
                  'truncations': truncated, 'timeout_reason': row.get('timeout_reason')}
        if row['status'] == 'provider_limit':
            verified = len(truncated) == 1 and truncated[0]['output_tokens'] == 8192 and truncated[0]['http_status'] == 200
            verified = verified and not errors and not pending
            report['classification'] = 'upstream_default_output_limit' if verified else 'needs_review'
        elif row['status'] == 'timeout':
            starts, arguments, tool_issues = {}, collections.Counter(), []
            for line in (path.parent / 'events.jsonl').open():
                if 'tool_execution_' not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                call_id = event.get('toolCallId')
                if event.get('type') == 'tool_execution_start':
                    starts[call_id] = event
                    arguments[json.dumps(event.get('args', {}), sort_keys=True)] += 1
                elif event.get('type') == 'tool_execution_end':
                    starts.pop(call_id, None)
                    text = ' '.join(str(c.get('text', '')) for c in event.get('result', {}).get('content', []))
                    for phrase in ('ModuleNotFoundError', 'ImportError', 'No space left', 'Out of memory',
                                   'Connection reset', 'Connection refused', 'Network is unreachable', 'Permission denied'):
                        matches = [line for line in text.splitlines() if phrase in line]
                        if matches:
                            tool_issues.extend(matches[-2:])
            report['maximum_identical_tool_calls'] = max(arguments.values(), default=0)
            report['unfinished_tools'] = [{'tool': event.get('toolName'),
                                          'timeout_seconds': event.get('args', {}).get('timeout'),
                                          'command_head': event.get('args', {}).get('command', '')[:160]}
                                         for event in starts.values()]
            report['tool_environment_messages'] = tool_issues
            report['stderr_bytes'] = (path.parent / 'stderr.log').stat().st_size
            report['api_seconds'] = sum(record.get('ended', record['started']) - record['started'] for record in records)
            confirmed = (row.get('timeout_reason') == 'wall_3600s' and not errors and not pending
                         and report['stderr_bytes'] == 0)
            report['classification'] = ('agent_combinatorial_search_wall_limit' if starts else 'agent_iteration_wall_limit') if confirmed else 'needs_review'
        else:
            report['classification'] = 'needs_review'
        if report['classification'] == 'needs_review':
            unresolved.append(row['id'])
        reports.append(report)
    assert len(reports) == 254
    assert all(sha(ROOT / path) == digest for path, digest in hashes.items())
    assert sha(score) == score_hash
    counts = dict(collections.Counter(row['classification'] for row in reports))
    summary = {'audited_cases': 254, 'classifications': counts, 'needs_review': unresolved,
               'confirmed_infrastructure_failure_ids': [], 'infrastructure_rerun_ids': [],
               'original_results_unchanged': True, 'original_scores_sha256': score_hash,
               'model_and_limits_unchanged': True,
               'networkx_note': 'BondNum_0213 requested optional NetworkX. It is absent in both the unchanged Codex and SoL-Pi Python environments; RDKit loads in both. The agent moved on to RDKit enumeration before wall timeout. This is not evidence of an infrastructure-specific failure.',
               'enumeration_note': 'BondNum_0213 builds set(permutations(labels)) on 13 labels (13! generated tuples before deduplication), rather than generating only unique permutations. BondNum_0127 runs repeated brute-force ring enumeration.',
               'policy': 'Only confirmed infrastructure-caused failures qualify for rerun; preserve model output limits and agent wall limits.',
               'time': time.time()}
    target = ROOT / 'failure_audit_20261006'
    target.mkdir(exist_ok=True)
    (target / 'cases.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2))
    (target / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (target / 'original_result_hashes.json').write_text(json.dumps(hashes, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
