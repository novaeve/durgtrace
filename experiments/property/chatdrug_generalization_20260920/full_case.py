# Frozen from pilot.py; full-task scoring hooks, original conversation/ReDF retained.
def run_case(case,db,outdir):
    start=time.monotonic();case_dir=outdir/case['id'];case_dir.mkdir(parents=True,exist_ok=True)
    if (case_dir/'result.json').exists():
        prev=json.loads((case_dir/'result.json').read_text())
        if prev.get('status')=='complete':return prev
    relay=Relay(case_dir/'api_calls.json')
    prompt=case['instruction']+' Give me five molecules in SMILES only and list them using bullet points. No explanation is needed.'
    initial_messages=[{'role':'system','content':'You are an expert in the field of molecular chemistry.'},{'role':'user','content':prompt}]
    result={'id':case['id'],'case':case,'status':'running','arms':{}}
    counter={'retrieval_property_evaluations':0,'retrieval_similarity_comparisons':0,'online_evaluations':0}
    try:
        initial=relay.complete(initial_messages,'shared_initial')
        first=score(case,parse_candidate(case['smiles'],initial))
        result['arms']['direct']={**first,'llm_calls_attributed':1}
        # Extract upstream functions verbatim, without importing unrelated peptide/protein stacks.
        first_pending=[True]
        def complete(messages,model,tokenizer,conversational_LLM,drug_type,round_index=None):
            if first_pending[0]:first_pending[0]=False;return initial
            return relay.complete(messages,f'chatdrug_feedback_{round_index}')
        def evaluate(input_drug,generated_drug,task,constraint,threshold_dict):
            counter['online_evaluations']+=1
            r=score(case,generated_drug)
            return bool(r['success']) if r['valid'] else -1
        def sim_sequence(task,a,b):
            counter['retrieval_similarity_comparisons']+=1
            return DataStructs.TanimotoSimilarity(fingerprint(a),fingerprint(b))
        # Same task-specific property direction as the upstream loose evaluator; memoized scalar calculation.
        def retrieval_evaluate(input_drug,generated_drug,task,constraint,threshold_dict):
            counter['retrieval_property_evaluations']+=1
            return retrieval_success(case, generated_drug)
        rn=load_functions(CD/'utils.py',['retrieve_and_feedback'],{'sim_sequence':sim_sequence,'evaluate':retrieval_evaluate})
        namespace={'sys':sys,'complete':complete,'parse':lambda task,inp,text,other:SM.parse_molecule(inp,text,other),
                   'evaluate':evaluate,'retrieve_and_feedback':rn['retrieve_and_feedback']}
        load_functions(CD/'main_ChatDrug.py',['conversation','ReDF'],namespace)
        record={case['smiles']:{'retrieval_conversation':[{'result':i} for i in range(3)],'skip_conversation_round':-1}}
        messages=[dict(m) for m in initial_messages];candidate=None;answer=0;rounds=0
        with (case_dir/'chatdrug.log').open('w') as logfile:
            for round_index in range(3):
                rounds+=1
                answer,candidate=namespace['conversation'](messages,None,None,'chatgpt',2,round_index,0,case['task'],
                    'molecule',case['smiles'],db,record,logfile,False,case['constraint'],{},None,None)
                if answer!=0 or candidate is None:break
        dump(case_dir/'chatdrug_trace.json',record)
        # Preserve the last actual generated SMILES, including invalid output for honest scoring.
        last_generated=None
        for turn in record[case['smiles']]['retrieval_conversation']:
            if 'generated_drug' in turn:last_generated=turn['generated_drug']
        result['arms']['chatdrug']={**score(case,last_generated),'llm_calls_attributed':rounds,
            'upstream_answer':int(answer),'upstream_skipped':answer==-1,**counter}
        independent=[first]
        for i in (() if relay.calls[0].get('stop_reason')=='refusal' else (1,2)):
            text=relay.complete(initial_messages,f'independent_{i+1}')
            independent.append(score(case,parse_candidate(case['smiles'],text)))
            if relay.calls[-1].get('stop_reason')=='refusal':break
        best=max(independent,key=lambda x:(x['success'],x['valid'],x['similarity'] if x['similarity'] is not None else -1,x['delta'] if x['delta'] is not None else -1e9))
        result['arms']['independent3']={**best,'llm_calls_attributed':len(independent),'candidates':independent}
        result['status']='complete'
    except Exception as e:
        result['status']='error';result['error_type']=type(e).__name__
        result['error']=str(e) if isinstance(e,RelayError) else 'See sanitized stage diagnostics'
    result['seconds']=round(time.monotonic()-start,3)
    result['api_requests']=sum(len(c.get('attempts',[])) for c in relay.calls)
    result['logical_llm_calls']=len(relay.calls)
    result['retry_attempts']=sum(max(0,len(c.get('attempts',[]))-1) for c in relay.calls)
    result['usage']={k:sum(a.get('usage',{}).get(k,0) or 0 for c in relay.calls for a in c.get('attempts',[])) for k in ['input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens']}
    result['response_models']=sorted({c['response_model'] for c in relay.calls if c.get('response_model')})
    result['truncated_responses']=sum(c.get('stop_reason')=='max_tokens' for c in relay.calls)
    result['refusals']=sum(c.get('stop_reason')=='refusal' for c in relay.calls)
    dump(case_dir/'result.json',result)
    emit({'case':case['id'],'status':result['status'],'success':{k:v['success'] for k,v in result['arms'].items()},'seconds':result['seconds']})
    return result
