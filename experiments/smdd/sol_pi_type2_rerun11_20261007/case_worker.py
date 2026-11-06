"""One task per OS process so abandoned HTTP handlers cannot leak into later tasks."""
from pathlib import Path
import json
import os
import sys
import run

ROOT = Path(__file__).resolve().parent


if __name__ == '__main__':
    task = sys.argv[1]
    case = next(case for case in json.loads((ROOT / 'type2/public_cases.json').read_text()) if case['id'] == task)
    run.dump(ROOT / 'type2/runs/solpi' / task / 'worker_process.json',
             {'pid': os.getpid(), 'pgid': os.getpgrp(), 'task': task})
    run.job('type2', case)
