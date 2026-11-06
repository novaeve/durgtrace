from pathlib import Path
import json,hashlib,collections,sys,tempfile,re,uuid,shlex
from runtime import CPU,ROOT,dump
from pharmacophore_3d import evaluate_3d_pharmacophore
OUT=ROOT/'audit_comparison';OUT.mkdir(exist_ok=True)
old_script=r'''
from pathlib import Path
import json,hashlib,collections
b=Path('/home/chenfuxin/smdd-migration');tasks=b/'SMDD-Bench/tasks'
roots={'claude':b/'smdd-assets/experiments/step_06_claude_type2_full_20260820/results/claude_type2_full_20260820','codex':b/'smdd-assets/experiments/H1-normal_codex_type2_20260901/results/codex_type2_native_20260901'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'methods':{},'hashes':{}}
for p in sorted(tasks.glob('smdd_002_*')):
 result['hashes'][p.name]={n:sha(p/n) for n in ['task.yaml','receptor.pdb','ground_truth.json']}
result['metric_sha256']=sha(b/'SMDD-Bench/metrics/pharmacophore_3d.py')
for method,root in roots.items():
 rows=[]
 for p in sorted(root.glob('smdd_002_*')):
  if not p.is_dir():continue
  row={'task':p.name,'solution':(p/'solution.csv').read_text() if (p/'solution.csv').exists() else '', 'result':json.loads((p/'agent_result.json').read_text())}
  if (p/'trajectory.jsonl').exists():
   events=[json.loads(l) for l in (p/'trajectory.jsonl').read_text().splitlines()]
   row['prompts']={e['event']:e['content'] for e in events if e['event']=='system_prompt' or e['event']=='user_message' and e.get('turn')==0}
   row['tools']=[{'turn':e['turn'],'tool':e['tool'],'input':e.get('input'),'output':(p/e['output_full']['artifact_path']).read_text() if e.get('output_full') else e.get('output_truncated','')} for e in events if e['event']=='tool_call']
  if (p/'run_manifest.json').exists():row['manifest']=json.loads((p/'run_manifest.json').read_text())
  rows.append(row)
 result['methods'][method]=rows
print(json.dumps(result))
'''
c=CPU()
try:
    _,stdout,stderr=c.c.exec_command(shlex.join(['python3','-c',old_script]),timeout=120)
    raw=stdout.read().decode();err=stderr.read().decode()
    assert stdout.channel.recv_exit_status()==0,err
    old=json.loads(raw)
    image=c.checked(['docker','image','inspect','smdd-agent:latest','--format','{{.Id}}']).strip()
    clean=c.checked(['docker','run','--rm','--network','none','--read-only','smdd-agent:latest','bash','-c',"find / -type f \\( -name 'ground_truth.json' -o -name 'task.yaml' -o -name '*type2*' \\) 2>/dev/null | head -80"],120)
finally:c.close()
dump(OUT/'old_evidence.json',old)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
hash_errors=[]
for tid,hashes in old['hashes'].items():
    for name,value in hashes.items():
        if sha(ROOT/'tasks'/tid/name)!=value:hash_errors.append(tid+'/'+name)
stats={};deep=[];prompts_equal=[];configs_equal=[];suspect=[]
for p in sorted((ROOT/'runs/deepseek').glob('smdd_002_*')):
    events=[json.loads(l) for l in (p/'trajectory.jsonl').read_text().splitlines()]
    row={'task':p.name,'solution':(p/'solution.csv').read_text(),'result':json.loads((p/'result.json').read_text())['details']}
    row['tools']=[{'turn':e['turn'],'tool':e['tool'],'input':e.get('input'),'output':(p/e['output_full']['artifact_path']).read_text() if e.get('output_full') else e.get('output_truncated','')} for e in events if e['event']=='tool_call']
    row['prompts']={e['event']:e['content'] for e in events if e['event']=='system_prompt' or e['event']=='user_message' and e.get('turn')==0}
    cr=next(x for x in old['methods']['claude'] if x['task']==p.name)
    prompts_equal.append(row['prompts']==cr['prompts'])
    config=json.loads((p/'config.json').read_text());cc=cr['manifest']['agent_config'];configs_equal.append({k:v for k,v in config.items() if k!='model'}=={k:v for k,v in cc.items() if k!='model'})
    for t in row['tools']:
        text=json.dumps(t['input'])+'\n'+t['output']
        hits=[term for term in ['ground_truth','smdd-migration','/data2/chenfuxin','eval_claude','codex_type2','scores.json','evaluation.json','/home/chenfuxin','/root/smdd'] if term in text]
        if hits:suspect.append({'task':p.name,'turn':t['turn'],'tool':t['tool'],'hits':hits,'input':t['input'],'output_excerpt':t['output'][:1000]})
    deep.append(row)
allrows={**old['methods'],'deepseek':deep}
for method,rows in allrows.items():
    results=[];tools=collections.Counter();errors=collections.Counter();boltz=[]
    for row in rows:
        p=OUT/method/row['task'];p.mkdir(parents=True,exist_ok=True);(p/'solution.csv').write_text(row['solution'])
        ev=evaluate_3d_pharmacophore(str(p/'solution.csv'),str(ROOT/'tasks'/row['task']/'ground_truth.json'))
        ev['task']=row['task'];results.append(ev)
        for t in row.get('tools',[]):
            tools[t['tool']]+=1
            if 'Traceback (most recent call last)' in t['output']:errors['traceback_tool_outputs']+=1
            if t['tool']=='predict_boltz':boltz.append({'task':row['task'],'turn':t['turn'],'output':t['output'][:900]})
        # Proximity to receptor atoms is an observation, not a standalone cause.
        atoms=[]
        for line in (ROOT/'tasks'/row['task']/'receptor.pdb').read_text().splitlines():
            if line.startswith(('ATOM  ','HETATM')):
                try:atoms.append([float(line[30:38]),float(line[38:46]),float(line[46:54])])
                except ValueError:pass
        import numpy as np
        from pharmacophore_3d import parse_agent_csv
        nearest=[float(np.linalg.norm(np.array(atoms)-q['coords'],axis=1).min()) for q in parse_agent_csv(p/'solution.csv')]
        ev['nearest_receptor_atom_distances']=nearest
    stats[method]={'tasks':len(results),'correct_points':sum(x['n_correct'] for x in results),'passed_tasks':sum(x['score']==1 for x in results),'distribution':dict(collections.Counter(x['n_correct'] for x in results)),'points_on_receptor_atoms_within_0_2A':sum(d<.2 for x in results for d in x['nearest_receptor_atom_distances']),'tool_calls':dict(tools),'tool_errors':dict(errors),'boltz_outputs':boltz,'tasks_scored':results}
report={'same_inputs_and_gold':not hash_errors,'hash_errors':hash_errors,'metric_identical':old['metric_sha256']==sha(ROOT/'pharmacophore_3d.py'),'claude_deepseek_identical_prompts':sum(prompts_equal),'identical_nonmodel_configs':sum(configs_equal),'current_cpu_image':image,'image_hidden_file_search':clean,'deepseek_suspect_access':suspect,'methods':stats}
dump(OUT/'comparison.json',report);dump(OUT/'deepseek_evidence.json',deep)
print(json.dumps({k:v for k,v in report.items() if k!='methods'}))
for method,s in stats.items():print(method,json.dumps({k:v for k,v in s.items() if k not in ['tasks_scored','boltz_outputs']}))
print('boltz_samples',json.dumps({m:s['boltz_outputs'][:2] for m,s in stats.items()}))
