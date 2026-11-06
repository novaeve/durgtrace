import hashlib,json,os,pathlib,subprocess,sys,time,yaml
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'harness'))
from agent_harness import run,agent_loop
from agent_harness.config import AgentConfig
from agent_harness.prompts import build_system_prompt,TOOL_SCHEMAS
from transport_adapter import complete
from gpu_transport import predict
BASE=pathlib.Path('/home/chenfuxin/smdd-migration')
TASKS=BASE/'SMDD-Bench/tasks'
HISTORY=BASE/'smdd-assets/experiments/step_07_claude_type4_paper_stratified20_20260823/run'
def sha(text):return hashlib.sha256(text.encode()).hexdigest()

def parity():
    records=[]
    for tid in (ROOT/'selected_tasks.txt').read_text().splitlines():
        if not tid:continue
        config=json.loads((HISTORY/tid/'run_manifest.json').read_text())['agent_config']
        history=[]
        with (HISTORY/tid/'trajectory.jsonl').open() as f:
            for line in f:
                e=json.loads(line)
                if e.get('event') in ('system_prompt','user_message'):
                    history.append(e)
                    if len(history)==2:break
        task=yaml.safe_load((TASKS/tid/'task.yaml').read_text())
        system=build_system_prompt(AgentConfig())
        user=f"## Task\n\n{task['description']}\n\nYour workspace at /workspace contains the task files. Start by examining them."
        assert len(history)==2,(tid,'missing initial messages')
        assert history[0]['content']==system,(tid,'system mismatch')
        assert history[1]['content']==user,(tid,'user mismatch')
        for k,v in {'max_turns':100,'max_tokens':10000000,'admet_budget':15,'boltz_budget':8,'temperature':1.0,'seed':42}.items():assert config[k]==v,(tid,k)
        records.append({'task':tid,'system_sha256':sha(system),'user_sha256':sha(user),'budgets_matched':True})
    assert len(records)==20
    (ROOT/'parity.json').write_text(json.dumps({'passed':True,'tasks':records,'tool_schema_sha256':sha(json.dumps(TOOL_SCHEMAS,sort_keys=True))},indent=2))
    print('PARITY PASSED: 20/20 system prompts, initial user messages and budgets',flush=True)

def evaluate(tid,out):
    resultdir=ROOT/'evaluator'/tid;resultdir.mkdir(parents=True,exist_ok=True)
    queue=ROOT/'eval_queue'/tid;queue.mkdir(parents=True,exist_ok=True)
    cmd=['docker','run','--rm','--network','none','--entrypoint','python',
        '-v',str(TASKS/tid)+':/eval/task:ro','-v',str(out)+':/eval/output:ro',
        '-v',str(resultdir)+':/eval/results','-v',str(queue)+':/queue',
        '-v',str(ROOT/'eval_bridge.py')+':/bridge.py:ro','smdd-evals:359ef1d7','/bridge.py']
    with (resultdir/'container.log').open('w') as log:
        process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            for request in queue.glob('*/request.json'):
                done=request.parent/'done.json'
                if done.exists():continue
                data=json.loads(request.read_text())
                try:r={'affinity':predict(data['payload'],request.parent/'gpu',data['samples'],42)}
                except Exception as e:r={'error':type(e).__name__}
                temp=done.with_suffix('.tmp');temp.write_text(json.dumps(r));temp.replace(done)
            time.sleep(1)
    result=json.loads((resultdir/'result.json').read_text())
    print('EVALUATOR',result['status'],flush=True)
    return result

if __name__=='__main__':
    parity()
    if '--preflight-only' in sys.argv:raise SystemExit(0)
    tid='smdd_004_ABL1_1';out=ROOT/'run'/tid
    if (out/'agent_result.json').exists():raise RuntimeError('Refuse to overwrite existing smoke')
    config=AgentConfig();config.model='deepseek/deepseek-flash'
    os.environ['CHATDRUG_DEEPSEEK_ENV']=str(ROOT/'private/deepseek.env')
    agent_loop.call_llm_completions=complete
    run.ensure_network();proxy=run.start_proxy()
    print('START',tid,flush=True)
    result=run.run_single_task(tid,0,str(TASKS),config,str(ROOT/'run'),proxy,7)
    print('AGENT',json.dumps(result),flush=True)
    if not (out/'solution.smi').exists():raise RuntimeError('No submitted molecule; do not expand')
    assessed=evaluate(tid,out)
    ok=result['status']=='submitted' and assessed['status']!='errored'
    (ROOT/'smoke_gate.json').write_text(json.dumps({'passed':ok,'task':tid,'agent_status':result['status'],'evaluator_status':assessed['status'],
        'admet_calls':result['admet_calls'],'boltz_calls':result['boltz_calls'],'note':'Gate checks execution, not task success.'},indent=2))
    raise SystemExit(0 if ok else 2)
