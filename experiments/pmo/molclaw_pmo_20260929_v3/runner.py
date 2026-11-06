"""MolClaw PMO rerun: same episode recovery, bounded oracle, validated finish."""
import ast
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from oracle_server import OracleService, LEGACY, SUBMISSION, TASKS, canonical
from pmo_common import dump, sha
from trajectory import complete_auc
from stall_watchdog import run_native, partial_result, progress
from validation import final_answer, audit

ROOT=Path(__file__).resolve().parent
MOL=Path('/data2/chenfuxin/molclaw_20260924');UP=MOL/'source/MolClaw-main'
PY=str(LEGACY/'venv/bin/python');MODEL='deepseek-v4.1-flash'


def setup(task,out,control):
    for path,digest in json.loads((LEGACY/'prepared/dependencies.json').read_text()).items():
        if sha(path)!=digest:raise RuntimeError('Oracle dependency changed: '+path)
    source=SUBMISSION/'runs/deepseek'/task/'0/answers.jsonl'
    seed=json.loads(source.read_text().splitlines()[0]);assert seed['index']==1
    service=OracleService(control,task)
    if not service.ledger().rows:service.score([seed['raw']],'initial_model_answer')
    initial=service.ledger().rows[0]
    shutil.copytree(UP/'skills',out/'.claude/skills',dirs_exist_ok=True)
    config={'method':'molclaw','task':task,'seed':0,'model':MODEL,'oracle_query_budget':1000,
            'initial_source':str(source),'initial_answer':seed['raw'],'workflow':'one native episode; resume incomplete output in same session',
            'duplicate_queries_consume_budget':True,'invalid_queries_consume_budget':True,
            'external_scoring_counted':True,'sources':{p.name:sha(p) for p in ROOT.glob('*.py')}}
    dump(control/'config.json',config)
    dump(control/'mcp.json',{'mcpServers':{
        'molclaw-scp':{'type':'stdio','command':PY,'args':[str(ROOT/'scp_gateway.py'),str(control),task]},
        'pmo':{'type':'stdio','command':PY,'args':[str(ROOT/'oracle_server.py'),str(control),task]}}})
    dump(control/'settings.json',{'hooks':{'PreToolUse':[{'matcher':'Bash|Read|Write|Edit|MultiEdit|Glob|Grep',
          'hooks':[{'type':'command','command':PY+' '+str(ROOT/'guard.py'),'timeout':20}]}]}})
    tree=ast.parse((UP/'molclaw_run/infer/claude_agent/run_claude.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_build_prompt')
    ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'upstream_prompt','exec'),ns)
    query=(f'PMO molecular optimization objective: {task}. {TASKS[task][1]} '
           f'Scores range from 0 to 1; higher is better. Improve this starting molecule: {seed["raw"]}. '
           f'Its official score is {initial["score"]}. Initialization used 1 of the 1000 shared oracle submissions. '
           'Use native MolClaw skills and tools. All objective scores, including references, duplicates and feedback, '
           'must use the PMO score_molecules tool or the wrapped SCP scoring tools. Wrapped tools charge the same ledger. '
           'Do not implement the objective or a surrogate locally, including Gaussian descriptor combinations or fingerprint similarity. '
           'Local structural generation, RDKit validation and individual property inspection are allowed. '
           'Native molecular generation tools (including min_similarity parameters) remain available. '
           'You MUST complete exactly 1000 candidate submissions and scoring responses. Early termination is forbidden, even at score 1.0. Continue exploring and improving the top 10 diverse candidates. Do not pad the budget with deliberate repeats or invalid molecules. '
           'Do not start independent episodes. Upon exhaustion return the best already evaluated molecule. '
           'A summary, plan or placeholder is not a final answer. Save result.md then explicitly submit one final SMILES.')
    prompt=ns['_build_prompt'](query,'Submit exactly ONE final molecule inside <answer>SMILES</answer>.','both',None)
    (out/'prompt.txt').write_text(prompt)
    return prompt


def job(task):
    out=ROOT/'runs'/task/'0';control=ROOT/'control'/task/'0'
    out.mkdir(parents=True,exist_ok=True);control.mkdir(parents=True,exist_ok=True)
    with (control/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (control/'result.json').exists():return json.loads((control/'result.json').read_text())
        if progress(control):return partial_result(control,task)
        state=json.loads((control/'state.json').read_text()) if (control/'state.json').exists() else {'session_id':str(uuid.uuid4()),'next_segment':0,'started':time.time(),'recovery_events':[]}
        prompt=setup(task,out,control)
        env=dict(os.environ);env.pop('ANTHROPIC_API_KEY',None);env.pop('SCP_HUB_API_KEY',None)
        env.update(ANTHROPIC_BASE_URL='http://127.0.0.1:18745',ANTHROPIC_AUTH_TOKEN='local-molclaw-proxy',
            ANTHROPIC_MODEL=MODEL,ANTHROPIC_DEFAULT_HAIKU_MODEL=MODEL,ANTHROPIC_DEFAULT_SONNET_MODEL=MODEL,
            ANTHROPIC_DEFAULT_OPUS_MODEL=MODEL,CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',MAX_THINKING_TOKENS='0',
            CLAUDE_CONFIG_DIR=str(control/'.runtime'),PMO_WORKSPACE_ROOT=str(out),PMO_CONTROL_DIR=str(control),
            OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        env['PATH']=str(MOL/'isolated_env/bin')+os.pathsep+env.get('PATH','');env['VIRTUAL_ENV']=str(MOL/'isolated_env')
        service=OracleService(control,task)
        for segment in range(state['next_segment'],2048):
            ledger=service.ledger()
            if segment:
                feedback=state.get('pending_reason','Your previous turn ended before a valid final submission.')
                prompt=(f'Continue the SAME PMO episode and existing oracle ledger. {feedback} '
                        f'The ledger currently contains {len(ledger.rows)} of 1000 submissions. Do not restart or replay prior evaluations. '
                        'If you only returned a summary or plan, execute the remaining native workflow. '
                        'If fewer than 1000 submissions have been scored, continue candidate generation and official scoring, even if you previously gave a final answer. Only at exactly 1000 submissions save process notes to result.md and submit exactly one valid '
                        '<answer>SMILES</answer> in your final response. Do not include placeholder tags or quote these instructions. '
                        'When budget is exhausted choose an already evaluated molecule.')
            state.update(status='running',segment=segment,next_segment=segment+1,updated=time.time(),pid=os.getpid())
            dump(control/'state.json',state)
            (control/f'prompt_{segment:02d}.txt').write_text(prompt)
            command=[str(MOL/'runtime/node_modules/.bin/claude'),'--dangerously-skip-permissions','-p','--model',MODEL,
                     '--output-format','stream-json','--verbose','--mcp-config',str(control/'mcp.json'),'--strict-mcp-config',
                     '--settings',str(control/'settings.json')]
            command += ['--session-id',state['session_id']] if segment==0 else ['--resume',state['session_id']]
            with (control/f'events_{segment:02d}.jsonl').open('w') as stdout,(control/f'stderr_{segment:02d}.log').open('w') as stderr:
                proc=run_native(control,command,input=prompt,text=True,cwd=out,env=env,stdout=stdout,stderr=stderr)
            if proc.stalled:return partial_result(control,task)
            events=[]
            for line in (control/f'events_{segment:02d}.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            final=next((e for e in reversed(events) if e.get('type')=='result'),{})
            native={'returncode':proc.returncode,'is_error':final.get('is_error'),'subtype':final.get('subtype'),'stop_reason':final.get('stop_reason')}
            dump(control/f'exit_{segment:02d}.json',native)
            answer=final_answer(final.get('result','')) if not proc.returncode and not final.get('is_error') else None
            if len(service.ledger().rows) < 1000:
                answer=None;reason='The 1000-submission experiment is incomplete. Generate further candidates and score them with the remaining budget. Do not stop or pad with deliberate repeats.'
            elif answer and not (out/'result.md').exists():
                answer=None;reason='A valid final answer was returned, but required result.md is missing. Finish reporting only.'
            elif not answer:reason='No unambiguous valid final molecule was submitted. A summary/plan/placeholder is not completion.'
            else:
                ledger=service.ledger();sm=canonical(answer)
                if sm not in ledger.buffer:
                    if ledger.exhausted:
                        answer=None;reason='The submitted final molecule has never been evaluated and budget is exhausted. Choose an evaluated molecule.'
                    else:service.score([answer],'final_output');ledger=service.ledger()
                if answer:
                    report=audit(control,ledger)
                    if not report['passed'] or not report['budget_within_cap']:raise RuntimeError('Receipt audit failed: '+str(report))
                    dump(control/'audit.json',report)
                    auc,curve=complete_auc(ledger.rows)
                    dump(control/'top10_trajectory.json',curve)
                    result={'method':'molclaw','task':task,'seed':0,'status':'validated_finished',
                            'experiment_finished':True,'final_valid':True,'final_evaluated':True,'final_answer':answer,
                            'final_score':ledger.buffer[sm][0],**ledger.metrics(),
                            'oracle_submissions':len(ledger.rows),'physical_oracle_evaluations':len(ledger.buffer),
                            'auc_top10':auc,'auc_top10_mt_mol':auc,'auc_protocol':'trapezoid over all 1000 actual submissions; unique valid top10; no unobserved tail',
                            'recovery_segments':segment,'session_id':state['session_id'],'time':time.time(),
                            'budget_sources':dict(__import__('collections').Counter(r['event_id'].split('/')[-1] for r in ledger.rows)),
                            'receipt_audit_passed':True}
                    dump(control/'result.json',result)
                    state.update(status='validated_finished');dump(control/'state.json',state)
                    return result
            state['recovery_events'].append({'segment':segment,'reason':reason,'native':native,'queries':len(service.ledger().rows)})
            state.update(status='recovering',pending_reason=reason);dump(control/'state.json',state)
            print(json.dumps({'task':task,'action':'resume_same_session','segment':segment,'reason':reason}),flush=True)
        state.update(status='needs_attention');dump(control/'state.json',state)
        raise RuntimeError('Native episode remained incomplete after 2048 resume segments; no success recorded')


def suite(tasks):
    with (ROOT/'suite.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        results={};errors={}
        dump(ROOT/'summary.json',{'validated_finished':0,'expected':len(tasks),'results':{},'errors':{}})
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            futures={pool.submit(job,t):t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                task=futures[future]
                try:results[task]=future.result()
                except Exception as error:errors[task]={'type':type(error).__name__,'error':str(error)}
                dump(ROOT/'summary.json',{'validated_finished':sum(r['status']=='validated_finished' for r in results.values()),'skipped_stalled':sum(r['status']=='skipped_stalled' for r in results.values()),'processed':len(results),'expected':len(tasks),'results':results,'errors':errors})
                print(json.dumps({'task':task,'validated':task in results,'error':errors.get(task)}),flush=True)
        if errors:raise RuntimeError(str(errors))


if __name__=='__main__':
    if sys.argv[1]=='full':suite(list(TASKS))
    elif sys.argv[1]=='pilot':suite(['qed','valsartan_smarts','mestranol_similarity','fexofenadine_mpo'])
    else:print(json.dumps(job(sys.argv[1])),flush=True)
