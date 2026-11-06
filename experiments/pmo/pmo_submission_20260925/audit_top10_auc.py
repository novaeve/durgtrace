"""Recompute final MT-Mol-style Top-10 AUC from persisted oracle submissions."""
import ast
import hashlib
import json
import math
from pathlib import Path
import statistics
import numpy as np

ROOT = Path(__file__).resolve().parent
REPORT = ROOT/'analysis_top10_auc'
SOURCE = REPORT/'source_mt_mol_auc.py'
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'top_auc')
namespace = {'np': np}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
top_auc = namespace['top_auc']
all_rows = []
groups = {}
for method, base, filename in [('deepseek', 'runs', 'answers.jsonl'),
                               ('chatdrug', 'runs_oracle_1k', 'oracle_queries.jsonl'),
                               ('agentdrug', 'runs_oracle_1k', 'oracle_queries.jsonl')]:
    rows = []
    folders = sorted((ROOT/base/method).glob('*/0'))
    assert len(folders) == 23
    for folder in folders:
        result = json.loads((folder/'result.json').read_text())
        assert result['status'] in ['complete', 'budget_exhausted', 'native_finished']
        path = folder/filename
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert 0 < len(records) <= 1000
        buffer = {}
        for index, record in enumerate(records, 1):
            assert record['index'] == index
            canonical, score = record['canonical'], record['score']
            assert math.isfinite(score) and 0 <= score <= 1
            if canonical is None:
                assert record['status'] == 'invalid'
                continue
            if canonical in buffer:
                assert score == buffer[canonical][0]
            else:
                buffer[canonical] = [score, index]
        auc = float(top_auc(buffer, 10, True, 1, 1000)) if buffer else 0.0
        recorded = result.get('auc_mt_mol_finish_true', result['auc_top10_mt_mol'])
        assert math.isclose(auc, recorded, abs_tol=1e-10)
        row = {'method': method, 'task': folder.parent.name, 'replicate': 0,
               'oracle_submissions': len(records), 'unique_valid': len(buffer),
               'status': result['status'], 'top10_auc': auc,
               'trace_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        rows.append(row)
        all_rows.append(row)
    groups[method] = {'tasks': 23, 'mean_top10_auc': statistics.mean(r['top10_auc'] for r in rows),
                      'sum_top10_auc': sum(r['top10_auc'] for r in rows),
                      'oracle_submissions': sum(r['oracle_submissions'] for r in rows)}
audit = {'budget': 1000, 'top_n': 10, 'freq_log': 1, 'finish': True,
         'early_termination': 'hold final top10 mean through query 1000',
         'duplicate_policy': 'keep canonical molecule at first original query index',
         'queries_included': 'all oracle submissions, including reference and feedback queries',
         'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
         'all_69_recomputed_values_match_recorded_final_values': True,
         'summary': groups, 'per_task': all_rows}
(REPORT/'top10_auc_recomputed.json').write_text(json.dumps(audit, indent=2))
lines = ['# Top-10 AUC', '', '单次实验；23 目标等权；每目标最多 1,000 次 oracle 提交。',
         '使用保存的 MT-Mol top_auc 源函数，freq_log=1、finish=True。提前结束保持最终 Top-10 均分延伸到 1,000 次。',
         '规范化去重保留首次查询序号，内部参考/反馈查询也计入轨迹。', '',
         '| 方法 | 23 目标平均 AUC（0–1） | 23 目标 AUC 总和（0–23） |', '|---|---:|---:|']
for method, values in groups.items():
    lines.append(f"| {method} | {values['mean_top10_auc']:.6f} | {values['sum_top10_auc']:.6f} |")
lines += ['', 'AgentDrug 的预算全部在起点与参考库评分阶段用完，未执行编辑生成；其 AUC 不是编辑生成效果。',
          'ChatDrug 有 19 题自然提前结束，4 题用满预算。上述值含提前结束后的持平补尾。',
          '69 条轨迹全部重算，与已记录的同口径最终数值一致。', '',
          '| 目标 | DeepSeek | ChatDrug | AgentDrug |', '|---|---:|---:|---:|']
lookup = {(r['method'], r['task']): r['top10_auc'] for r in all_rows}
for task in sorted({r['task'] for r in all_rows}):
    lines.append('| '+task+' | '+' | '.join(f'{lookup[(method, task)]:.6f}' for method in groups)+' |')
(REPORT/'Top10_AUC结果.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(json.dumps(groups, indent=2))
print('Verified all 69 trajectories against recorded final AUC values.')
