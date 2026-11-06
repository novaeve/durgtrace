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
                    input_mol = Chem.MolFromSmiles(batch["smiles"])
                    output_mol = Chem.MolFromSmiles(output["pred"][0])
                    if "single" in args.data:
                        input_prop = task2func[prop](input_mol)
                        output_prop = task2func[prop](output_mol)
                        if prop == "LogP+":
                            hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                            property_feedback = f"The modified molecule has a LogP value of {round(output_prop, 4)} and the original one has a LogP value of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "LogP-":
                            hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                            property_feedback = f"The modified molecule has a LogP value of {round(output_prop, 4)} and the original one has a LogP value of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "TPSA+":
                            hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                            property_feedback = f"The modified molecule has a topological polar surface area (TPSA) of {round(output_prop, 4)} and the original one has a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "TPSA-":
                            hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                            property_feedback = f"The modified molecule has a topological polar surface area (TPSA) of {round(output_prop, 4)} and the original one has a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "HBD+":
                            hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                            property_feedback = f"The modified molecule has {output_prop} hydrogen bond donors and the original one has {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                        if prop == "HBD-":
                            hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                            property_feedback = f"The modified molecule has {output_prop} hydrogen bond donors and the original one has {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                        if prop == "HBA+":
                            hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                            property_feedback = f"The modified molecule has {output_prop} hydrogen bond acceptors and the original one has {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                        if prop == "HBA-":
                            hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                            property_feedback = f"The modified molecule has {output_prop} hydrogen bond acceptors and the original one has {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                        if prop == "QED+":
                            hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                            property_feedback = f"The modified molecule has a drug-likeness of {round(output_prop, 4)} and the original one has a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "QED-":
                            hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                            property_feedback = f"The modified molecule has a drug-likeness of {round(output_prop, 4)} and the original one has a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "MR+":
                            hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                            DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                            property_feedback = f"The modified molecule has a molar refractivity of {round(output_prop, 4)} and the original one has a molar refractivity of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if prop == "MR-":
                            hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                            DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                            property_feedback = f"The modified molecule has a molar refractivity of {round(output_prop, 4)} and the original one has a molar refractivity of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                    if "multi" in args.data:
                        logp, prop = prop[:5], prop[5:]
                        input_logp, input_prop = task2func[logp](input_mol), task2func[prop](input_mol)
                        output_logp, output_prop = task2func[logp](output_mol), task2func[prop](output_mol)
                        if logp == "LogP+":
                            if prop == "TPSA+":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                            if prop == "TPSA-":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                            if prop == "HBD+":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                            if prop == "HBD-":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                            if prop == "HBA+":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                            if prop == "HBA-":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                            if prop == "QED+":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                            if prop == "QED-":
                                hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                        if logp == "LogP-":
                            if prop == "TPSA+":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                            if prop == "TPSA-":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                            if prop == "HBD+":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                            if prop == "HBD-":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                            if prop == "HBA+":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                            if prop == "HBA-":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                            if prop == "QED+":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                            if prop == "QED-":
                                hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop)]
                                property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
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
