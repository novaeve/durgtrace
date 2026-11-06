def run_core(args,batch,model,test_dataset,code_executor_agent=None):
    eval_outputs=[]
    validity_work=0
    total_work=0
    prop = args.data.split("/")[-1]
    ori_prompt = batch['prompt']
    max_steps = args.refine_steps + 1
    for i in range(1, max_steps + 1):
        prop = args.data.split("/")[-1]
        total_work += 1
        output = model.inference(listize_fn(batch))
        output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
        output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
        if i < max_steps:
            try:
                validity_feedback = get_validity_feedback(output["pred"][0], code_executor_agent)
                if "Error" in validity_feedback or "not chemically valid" in validity_feedback:
                    validity_work += 1
                    feedback_output = "Validity:\n{}".format(validity_feedback)
                else:
                    output_mol = Chem.MolFromSmiles(output["pred"][0])
                    hit, DB, property_feedback = s2_feedback(output["pred"][0], test_dataset)
                    if hit:
                        eval_outputs.append(output)
                        break
                    else:
                        try:
                            feedback_output = "Validity:\n{}\nDesired property:\n{}".format(validity_feedback, property_feedback)
                            DB["sim"] = DB["mol"].apply(lambda m: DataStructs.TanimotoSimilarity(AllChem.GetMorganFingerprint(output_mol, 2), AllChem.GetMorganFingerprint(m, 2)))
                            example = DB.sort_values(by=['sim'], ascending=False).iloc[0]["SMILES"]
                            feedback_output += f"\n\nFor your reference, we find a molecule {example} which is correct and similar to your modified molecule."
                        except:
                            pass
            except:
                continue
            batch['prompt'] = ori_prompt + output["pred"][0] + f"\n\nImprove the modified molecule based on the following feedback:\n{feedback_output}\nRespond with only the SMILES string of your modified molecule. No explanation is needed."
        else:
            eval_outputs.append(output)
    return eval_outputs, validity_work, total_work
