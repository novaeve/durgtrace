from pathlib import Path
import json,time,collections
r=Path('/data2/chenfuxin/smdd_deepseek_codex_type4_20261004');rows=[]
for p in sorted((r/'runs/codex').glob('*/record.json')):
 rec=json.loads(p.read_text())
 if rec['evaluation']!='not_evaluated':continue
 out=p.parent;agent=json.loads((out/'result.json').read_text());apis=sorted((out/'api').glob('*.json'))
 last=json.loads(apis[-1].read_text()) if apis else {};choice=last.get('response',{}).get('choices',[{}])[0]
 waits=[]
 for q in out.rglob('resource_wait.json'):
  waits.append(json.loads(q.read_text()))
 reason='agent_ended_without_submission'
 if agent['status']=='budget_exhausted':reason='agent_budget_exhausted'
 if agent['status']=='error' and 'timed out after 43199' in agent.get('error',''):reason='task_timeout'
 rows.append({'task':out.name,'agent_status':agent['status'],'reason':reason,
  'has_root_submission':(out/'solution.smi').exists(),'has_workspace_submission':(out/'workspace/solution.smi').exists(),
  'submitted':agent.get('submitted',False),'api_receipts':len(apis),'last_finish_reason':choice.get('finish_reason'),
  'last_provider_http':last.get('attempts',[{}])[-1].get('status'),'resource_wait_evidence':waits})
report={'time':time.time(),'unscored_count':len(rows),'eligible_for_score_only':sum(row['has_root_submission'] or row['has_workspace_submission'] for row in rows),'reason_counts':dict(collections.Counter(row['reason'] for row in rows)),'tasks':rows}
assert len(rows)==15
(r/'codex_reevaluation_audit_20261007.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
