"""PMO stdio MCP adapter. Every submitted molecule consumes one query."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time

LEGACY = Path('/data2/chenfuxin/pmo_1k_20260924')
SUBMISSION = Path('/data2/chenfuxin/pmo_submission_20260925')
sys.path[:0] = [str(LEGACY), str(SUBMISSION)]
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
from pmo_common import canonical, make_oracle
from submission_budget import SubmissionLedger
from task_specs import TASKS


class OracleService:
    def __init__(self, out, task, budget=1000, evaluator=None):
        self.out, self.task, self.budget = Path(out), task, budget
        self.evaluator = evaluator

    def ledger(self):
        def evaluate(sm):
            if self.evaluator is None:
                os.chdir(LEGACY)
                self.evaluator = make_oracle(TASKS[self.task][0])
            return self.evaluator(sm)
        return SubmissionLedger(self.out/'oracle_queries.jsonl', canonical, evaluate, self.budget)

    def score(self, molecules, source='agent_tool'):
        if not isinstance(molecules, list) or not all(isinstance(s, str) for s in molecules):
            raise ValueError('smiles must be a list of strings')
        with (self.out/'oracle.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger, rows = self.ledger(), []
            for sm in molecules:
                if ledger.exhausted:
                    break
                rows.append(ledger.submit(sm, f'query/{len(ledger.rows)+1}/{source}'))
            return {'results': rows, 'used': len(ledger.rows),
                    'remaining': ledger.budget-len(ledger.rows),
                    'budget_exhausted': ledger.exhausted,
                    'not_evaluated': len(molecules)-len(rows)}

    def score_external(self, molecules, source):
        # All-or-nothing reservation prevents an external batch exceeding the cap.
        with (self.out/'oracle.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger=self.ledger()
            if len(molecules)>ledger.budget-len(ledger.rows):
                raise ValueError(f'Insufficient oracle budget: {ledger.budget-len(ledger.rows)} remaining; reduce the molecule batch.')
            return [ledger.submit(sm,f'query/{len(ledger.rows)+1}/{source}') for sm in molecules]

    def handle(self, request):
        method, params = request['method'], request.get('params', {})
        if method == 'initialize':
            return {'protocolVersion': params.get('protocolVersion', '2024-11-05'),
                    'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'pmo-budget-oracle', 'version': '1.0.0'}}
        if method == 'ping':
            return {}
        if method == 'tools/list':
            return {'tools': [
                {'name': 'score_molecules',
                 'description': 'Evaluate molecules with the official PMO objective. Each molecule, including duplicates and invalid strings, consumes one of the shared 1000 queries. Partial batches stop at the hard cap. All objective evaluations must use this tool.',
                 'inputSchema': {'type': 'object', 'properties': {'smiles': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['smiles'], 'additionalProperties': False}},
                {'name': 'budget_status', 'description': 'Inspect remaining queries without evaluating molecules.',
                 'inputSchema': {'type': 'object', 'properties': {}}}]}
        if method == 'tools/call':
            try:
                if params['name'] == 'score_molecules':
                    result = self.score(params.get('arguments', {}).get('smiles'))
                elif params['name'] == 'budget_status':
                    ledger = self.ledger()
                    result = {'used': len(ledger.rows), 'remaining': ledger.budget-len(ledger.rows), 'budget': ledger.budget}
                else:
                    raise ValueError('Unknown tool')
                return {'content': [{'type': 'text', 'text': json.dumps(result)}], 'isError': False}
            except Exception as error:
                return {'content': [{'type': 'text', 'text': type(error).__name__+': '+str(error)}], 'isError': True}
        raise ValueError('Unsupported method')


def serve(service):
    for line in sys.stdin:
        request = json.loads(line)
        if 'id' not in request:
            continue
        try:
            result=service.handle(request)
            response = {'jsonrpc':'2.0','id':request['id'],'result':result}
            if request.get('method')=='tools/call':
                with (service.out/'mcp_receipts.jsonl').open('a') as f:
                    f.write(json.dumps({'time':time.time(),'server':type(service).__name__,'request':request,'result':result})+'\n')
                    f.flush();os.fsync(f.fileno())
        except Exception as error:
            response = {'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32603, 'message': str(error)}}
        print(json.dumps(response), flush=True)


if __name__ == '__main__':
    service = OracleService(sys.argv[1], sys.argv[2])
    serve(service)
