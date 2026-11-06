import json
import os
from pathlib import Path
from runner import ROOT, UP, MOL, MODEL, LEGACY, SUBMISSION, TASKS, sha, dump, canonical
from pmo_common import make_oracle

os.chdir(LEGACY)
initials = {}
for task in TASKS:
    path = SUBMISSION/'runs/deepseek'/task/'0/answers.jsonl'
    row = json.loads(path.read_text().splitlines()[0])
    assert row['index'] == 1 and canonical(row['raw']) is not None, task
    initials[task] = row['raw']
verified = json.loads((LEGACY/'prepared/dependencies.json').read_text())
for path, digest in verified.items():
    assert sha(path) == digest, path
skills = {str(p.relative_to(UP/'skills')): sha(p) for p in sorted((UP/'skills').rglob('*')) if p.is_file()}
dump(ROOT/'manifest.json', {
    'method': 'molclaw', 'model': MODEL, 'tasks': list(TASKS), 'seeds': [0],
    'oracle_query_budget': 1000, 'concurrency': 2,
    'completion_protocol': 'Exactly 1000 actual scored submissions per objective; no early completion or unobserved AUC tail',
    'initial_answers': initials, 'verified_dependencies': verified,
    'upstream_skills_sha256': skills,
    'upstream_prompt_source_sha256': sha(UP/'molclaw_run/infer/claude_agent/run_claude.py'),
    'source_hashes': {p.name: sha(p) for p in ROOT.glob('*.py')},
    'supersedes': 'v1 and v2; all previous results excluded',
    'protocol_version':3})
print(json.dumps({'initial_answers_valid': len(initials), 'dependencies_verified': len(verified), 'skills_recorded': len(skills)}))
