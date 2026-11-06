from pathlib import Path
import json
import tempfile
import pandas as pd
from smdd_liddia_tools import BudgetGate, BudgetExhausted, GraphGATool, Pocket2MolTool

root = Path('/data2/chenfuxin/agent_reproduction_20260928')
report = {}
with tempfile.TemporaryDirectory() as td:
    calls = []
    def backend(s):
        calls.append(s)
        if s == 'N':
            raise RuntimeError('simulated backend failure')
        return {'test_score': 0.5}
    gate = BudgetGate(Path(td)/'budget.jsonl', {'admet': backend, 'boltz': backend},
                      {'admet': 2, 'boltz': 1})
    gate.predict('admet', 'C')
    try:
        gate.predict('admet', 'N')
    except RuntimeError:
        pass
    try:
        gate.predict('admet', 'O')
        raise AssertionError('budget exceeded')
    except BudgetExhausted:
        pass
    assert calls == ['C', 'N'] and gate.used['admet'] == 2
    report['budget_failure_consumes_attempt'] = True
    try:
        BudgetGate(Path(td)/'budget.jsonl', {})
        raise AssertionError('reset allowed')
    except FileExistsError:
        pass
    report['budget_reset_blocked'] = True
    df = pd.DataFrame({'SMILES':['CCO', 'CCCO', 'c1ccccc1', 'CC(=O)O']})
    tool = GraphGATool(seed=42)
    try:
        tool(df, 'Vina Score', 5, td)
        raise AssertionError('Vina accepted')
    except ValueError:
        pass
    report['vina_objective_rejected'] = True
    out, meta = tool(df, 'QED', 5, td, score_cap=12)
    assert 0 < len(out) <= 5 and meta['score_calls'] <= 12
    report['graphga'] = meta
    gate2 = BudgetGate(Path(td)/'shared.jsonl', {'admet': backend}, {'admet':3, 'boltz':1})
    gate2.predict('admet', 'C')  # explicit agent call shares the GA budget
    shared = GraphGATool({'ADMET-test':lambda s:gate2.predict('admet',s)['test_score']})
    out, meta = shared(df, 'ADMET-test', 5, td)
    assert gate2.used['admet'] == 3 and meta['score_calls'] == 2
    assert meta['stop'] == 'budget_exhausted:admet'
    report['shared_agent_ga_budget'] = True
report['note'] = 'Synthetic backends only test accounting, not real ADMET or Boltz.'
(root/'smoke/smdd_tools.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
