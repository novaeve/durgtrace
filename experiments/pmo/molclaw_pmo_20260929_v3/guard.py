"""Scientific protocol guard: inspect executable syntax, not words in prose.

This is not an adversarial security sandbox. Completed runs require a trace audit.
"""
import ast
import json
import os
from pathlib import Path
import re
import shlex
import sys

DENIED_MODULES = {'tdc', 'guacamol', 'sklearn', 'joblib', 'pickle', 'requests', 'httpx', 'urllib', 'socket', 'subprocess', 'ctypes', 'importlib'}
DENIED_CALLS = {'eval', 'exec', 'compile', 'system', 'popen', 'getattr', 'setattr'}
SCORING_CALLS = {'qed', 'weights_mean', 'weights_max', 'weights_none', 'tanimotosimilarity', 'bulktanimotosimilarity', 'dicesimilarity', 'fingerprintsimilarity', 'cosinesimilarity', 'oracle', 'make_oracle'}
AGGREGATORS = {'exp', 'expm1', 'prod', 'product', 'mean', 'sqrt', 'pow', 'power'}


def python_reason(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 'Python syntax could not be inspected; save a valid Python script and run it.'
    aliases = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split('.')[0] in DENIED_MODULES:
                    return 'Use the configured MCP tools for scoring, network access and external programs.'
                aliases[a.asname or a.name] = a.name
        if isinstance(n, ast.ImportFrom):
            if (n.module or '').split('.')[0] in DENIED_MODULES or any(a.name == '*' for a in n.names):
                return 'Use explicit structural imports; scoring services must use the budgeted MCP tools.'
            for a in n.names:
                aliases[a.asname or a.name] = (n.module or '')+'.'+a.name
    def name(n):
        if isinstance(n, ast.Name): return aliases.get(n.id, n.id)
        if isinstance(n, ast.Attribute): return name(n.value)+'.'+n.attr
        return ''
    chemistry = any('rdkit' in v.lower() for v in aliases.values())
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call): continue
        fn = name(n.func); leaf = fn.split('.')[-1].lower()
        if leaf == '__import__':
            if not (len(n.args)==1 and isinstance(n.args[0],ast.Constant) and n.args[0].value == 'rdkit'):
                return 'Dynamic imports are unavailable; use explicit imports.'
        if leaf in DENIED_CALLS:
            return 'Dynamic execution is unavailable in this benchmark; use ordinary explicit Python.'
        if leaf in SCORING_CALLS or 'fingerprint' in leaf or leaf in {'getonbits','getnonzeroelements'}:
            return 'Objective/fingerprint scoring must use the budgeted PMO or wrapped SCP tools. Structure generation and validation are allowed.'
        if leaf in {'exp','expm1','pow','power'}:
            return 'Do not reconstruct Gaussian/power objective factors from cached descriptors; use the budgeted oracle.'
        if chemistry and (leaf in AGGREGATORS or leaf in {'sc','score','scoring','proxy_score','surrogate_score','gaussian','similarity'}):
            return 'Do not reconstruct an objective or surrogate from descriptor terms. Use score_molecules; individual descriptor inspection is allowed.'
        if leaf.startswith('_') and leaf != '__import__':
            return 'Private/dynamic execution APIs are unavailable.'
    if any(isinstance(n,ast.BinOp) and isinstance(n.op,ast.Pow) for n in ast.walk(tree)):
        return 'Objective power/Gaussian reconstruction must use the budgeted oracle.'
    return None


def reason(data):
    root = Path(os.environ.get('PMO_WORKSPACE_ROOT', data.get('cwd', '.'))).resolve()
    cwd = Path(data.get('cwd', str(root))).resolve()
    tool = data.get('tool_name', ''); inp = data.get('tool_input', {})
    def inside(path):
        p = Path(path); p = p if p.is_absolute() else cwd/p
        try: p.resolve().relative_to(root); return True
        except ValueError: return False
    def readable_runtime_result(path):
        control=os.environ.get('PMO_CONTROL_DIR')
        if not control:return False
        p=Path(path);p=p if p.is_absolute() else cwd/p
        try:
            rel=p.resolve().relative_to(Path(control).resolve()/'.runtime')
            return 'tool-results' in rel.parts
        except ValueError:return False
    if tool in ('Read','Write','Edit','MultiEdit','Glob','Grep'):
        path = inp.get('file_path') or inp.get('path')
        if path and not inside(path) and not (tool=='Read' and readable_runtime_result(path)): return 'Use files under the fixed sample workspace: '+str(root)
        if tool in ('Write','Edit','MultiEdit') and path:
            rel=str((Path(path) if Path(path).is_absolute() else cwd/path).resolve().relative_to(root))
            if rel.startswith('.runtime') or rel in {'.mcp.json','settings.json'}:
                return 'Runtime configuration is managed by the benchmark.'
        return None
    if tool != 'Bash': return None
    command = inp.get('command', '')
    # Inspect paths in executable commands, using the immutable root (not changing cwd).
    for path in re.findall(r'/(?:data2|tmp|home|root|etc)/[^\s\"\x27;|<>]*', command):
        if not inside(path): return 'Use files under the fixed sample workspace: '+str(root)
    if re.search(r'(^|[;&|\n]\s*)(?:curl|wget|node|ruby|perl|ssh|scp|pip|conda|uv)\b', command):
        return 'Use the configured MCP tools for external services; do not install or invoke alternative runtimes.'
    if re.search(r'\b(?:python\w*|python[\d.]*)\s+-(?:m|S|I)\b',command):
        return 'Run a plain Python file or python -c in this workspace.'
    snippets=[]
    for match in re.finditer(r'<<-?\s*[\x27\"]?(\w+)[\x27\"]?[^\n]*\n(.*?)\n\1\b',command,re.S):
        prefix=command[max(0,command.rfind('\n',0,match.start())):match.start()]
        # Only executed Python heredocs, not writing notes or scripts.
        if re.search(r'\bpython[\w.]*\b',prefix) or ('.py' in prefix and re.search(r'\bpython[\w.]*\b',command[match.end():])): snippets.append(match.group(2))
    try: tokens=shlex.split(command)
    except ValueError: tokens=[]
    for i,t in enumerate(tokens):
        if re.fullmatch(r'(?:.*/)?python[\w.]*',t):
            if i+2<len(tokens) and tokens[i+1]=='-c': snippets.append(tokens[i+2])
            elif i+1<len(tokens) and tokens[i+1].endswith('.py'):
                path=Path(tokens[i+1]); path=path if path.is_absolute() else cwd/path
                if not inside(str(path)): return 'Python scripts must be inside the sample workspace.'
                if path.exists(): snippets.append(path.read_text())
    if re.search(r'\bpython[\w.]*\b', command):
        # Inspect imported workspace helpers, but not documentation, skills or runtime records.
        for path in root.rglob('*.py'):
            if any(s.startswith('.') for s in path.relative_to(root).parts): continue
            snippets.append(path.read_text(errors='replace'))
    for code in snippets:
        issue=python_reason(code)
        if issue: return issue
    return None


if __name__ == '__main__':
    data=json.load(sys.stdin); message=reason(data)
    control=Path(os.environ['PMO_CONTROL_DIR'])
    with (control/'guard_events.jsonl').open('a') as f:
        f.write(json.dumps({'tool':data.get('tool_name'),'input':data.get('tool_input'), 'cwd':data.get('cwd'),'decision':'deny' if message else 'allow','reason':message})+'\n')
    if message:
        print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':message}}))
