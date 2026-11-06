"""Reuse each benchmark's frozen DeepSeek API class without copying credentials."""
from pathlib import Path
import ast
import json
import time
import requests
from runtime import dump

ROOT = Path(__file__).resolve().parent
CLASSES = {}


def create(kind, out):
    if kind not in CLASSES:
        path = ROOT / 'source' / f'{kind}_transport.py'
        nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'API']
        assert len(nodes) == 1
        ns = dict(Path=Path, json=json, time=time, requests=requests, dump=dump)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
        CLASSES[kind] = ns['API']
    return CLASSES[kind](out)
