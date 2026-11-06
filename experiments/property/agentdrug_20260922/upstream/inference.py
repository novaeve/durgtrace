import os
import time
import tqdm
import torch

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import warnings; warnings.filterwarnings("ignore")

from source.config import parse_args_llm
from source.utils.help_funcs import seed_everything
from source.utils.help_funcs import collate_fn
from source.utils.help_funcs import _save_checkpoint, _reload_model
from source.datasets import *
from source.models import *
from source.utils.evaluation import *

import tempfile
from autogen.coding import LocalCommandLineCodeExecutor
from autogen import ConversableAgent
from utils import get_validity_feedback
temp_dir = tempfile.TemporaryDirectory()
executor = LocalCommandLineCodeExecutor(
    timeout=60,
    work_dir=temp_dir.name,
)
code_executor_agent = ConversableAgent(
    "code_executor_agent",
    llm_config=False,
    code_execution_config={"executor": executor},
    human_input_mode="NEVER",
)

def listize_fn(original_batch):
    batch = {}
    for k in original_batch.keys():
        batch[k] = [original_batch[k]]
    return batch

def main(args):
    seed = args.seed
    seed_everything(seed=seed)

    # Step 1: Build dataset
    test_dataset = load_dataset[args.dataset](path = args.path, data = args.data, split = "test", 
        hit_thres = args.hit_thres, DB_size = args.DB_size, 
    )

    # Step 2: Build model
    args.llm_path = get_llm_path[args.llm_name]
    model = load_model[args.model_name](args=args)
    if args.checkpoint_path is not None:
        model = _reload_model(model, args.checkpoint_path)

    # Step 3: Evaluating
    model.eval()
    eval_outputs = []
    progress_bar_test = tqdm.tqdm(range(len(test_dataset)))
    validity_work, total_work = 0, 1e-8

    start_time = time.time()
    for index in range(len(test_dataset)):
        batch = test_dataset[index]
        with torch.no_grad():
            if args.refine == "None":
                output = model.inference(listize_fn(batch))
                output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
                output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
                eval_outputs.append(output)
            elif args.refine == "self":
                prop = args.data.split("/")[-1]
                ori_prompt = batch['prompt']
                max_steps = args.refine_steps
                for i in range(1, max_steps + 1):
                    total_work += 1
                    output = model.inference(listize_fn(batch))
                    output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
                    output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
                    if i < max_steps:
                        feedback_batch = {
                            'id': 0,
                            'smiles': None,
                            'prompt': ori_prompt + output["pred"][0] + '\nEvaluate the modified molecule on its chemical validity and the desired property according to the requirement. Please provide two pieces of feedback. Start your feedback about validity with the phrase "Validity:", and start your feedback about the desired property with the phrase "Desired property:".',
                            'label': None,
                        }
                        feedback_output = model.inference(listize_fn(feedback_batch))['pred'][0].strip().replace("\n\n", "\n")
                        batch['prompt'] = ori_prompt + output["pred"][0] + f"\n\nImprove the modified molecule based on the following feedback:\n{feedback_output}\nRespond with only the SMILES string of your modified molecule. No explanation is needed."
                    else:
                        eval_outputs.append(output)
            elif args.refine == "chatdrug":
                prop = args.data.split("/")[-1]
                ori_prompt = batch['prompt']
                max_steps = args.refine_steps
                for i in range(1, max_steps + 1):
                    total_work += 1
                    output = model.inference(listize_fn(batch))
                    output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
                    output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
                    if i < max_steps:
                        try:
                            input_mol = Chem.MolFromSmiles(batch["smiles"])
                            output_mol = Chem.MolFromSmiles(output["pred"][0])
                            if output_mol is None:
                                eval_outputs.append(output)
                                break
                            else:
                                if "single" in args.data:
                                    input_prop = task2func[prop](input_mol)
                                    output_prop = task2func[prop](output_mol)
                                    if prop == "LogP+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "LogP-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "TPSA+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "TPSA-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "HBD+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "HBD-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "HBA+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "HBA-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "QED+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "QED-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                if "multi" in args.data:
                                    logp, prop = prop[:5], prop[5:]
                                    input_logp, input_prop = task2func[logp](input_mol), task2func[prop](input_mol)
                                    output_logp, output_prop = task2func[logp](output_mol), task2func[prop](output_mol)
                                    if logp == "LogP+":
                                        if prop == "TPSA+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "TPSA-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBD+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBD-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBA+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBA-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "QED+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "QED-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if logp == "LogP-":
                                        if prop == "TPSA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "TPSA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBD+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBD-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "QED+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "QED-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                if hit:
                                    eval_outputs.append(output)
                                    break
                                else:
                                    feedback_output = "The provided molecule is not correct. "
                                    DB["sim"] = DB["mol"].apply(lambda m: DataStructs.TanimotoSimilarity(AllChem.GetMorganFingerprint(output_mol, 2), AllChem.GetMorganFingerprint(m, 2)))
                                    example = DB.sort_values(by=['sim'], ascending=False).iloc[0]["SMILES"]
                                    feedback_output += f"We find a molecule {example} which is correct and similar to the provided molecule. "
                                    batch['prompt'] = ori_prompt + output["pred"][0] + f"\n{feedback_output}Can you give me a new molecule?\nRespond with only the SMILES string of your new molecule. No explanation is needed."
                        except:
                            eval_outputs.append(output)
                            break
                    else:
                        eval_outputs.append(output)
            elif args.refine == "chatdrug-e":
                prop = args.data.split("/")[-1]
                ori_prompt = batch['prompt']
                max_steps = args.refine_steps
                for i in range(1, max_steps + 1):
                    total_work += 1
                    output = model.inference(listize_fn(batch))
                    output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
                    output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
                    if i < max_steps:
                        try:
                            input_mol = Chem.MolFromSmiles(batch["smiles"])
                            output_mol = Chem.MolFromSmiles(output["pred"][0])
                            if output_mol is None:
                                eval_outputs.append(output)
                                break
                            else:
                                if "single" in args.data:
                                    input_prop = task2func[prop](input_mol)
                                    output_prop = task2func[prop](output_mol)
                                    if prop == "LogP+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "LogP-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "TPSA+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "TPSA-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "HBD+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "HBD-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "HBA+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "HBA-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if prop == "QED+":
                                        hit = output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                        DB = test_dataset.DB[test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0]]
                                    if prop == "QED-":
                                        hit = output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                        DB = test_dataset.DB[test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                if "multi" in args.data:
                                    logp, prop = prop[:5], prop[5:]
                                    input_logp, input_prop = task2func[logp](input_mol), task2func[prop](input_mol)
                                    output_logp, output_prop = task2func[logp](output_mol), task2func[prop](output_mol)
                                    if logp == "LogP+":
                                        if prop == "TPSA+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "TPSA-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBD+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBD-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBA+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBA-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "QED+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "QED-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                    if logp == "LogP-":
                                        if prop == "TPSA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "TPSA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBD+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBD-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "HBA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "HBA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                        if prop == "QED+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                        if prop == "QED-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                if hit:
                                    eval_outputs.append(output)
                                    break
                                else:
                                    feedback_output = "The provided molecule is not correct. "
                                    batch['prompt'] = ori_prompt + output["pred"][0] + f"\n{feedback_output}Can you give me a new molecule?\nRespond with only the SMILES string of your new molecule. No explanation is needed."
                        except:
                            eval_outputs.append(output)
                            break
                    else:
                        eval_outputs.append(output)
            elif args.refine == "agentdrug":
                prop = args.data.split("/")[-1]
                ori_prompt = batch['prompt']
                max_steps = args.refine_steps + 1
                for i in range(1, max_steps + 1):
                    total_work += 1
                    output = model.inference(listize_fn(batch))
                    output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
                    output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
                    if i < max_steps:
                        try:
                            validity_feedback = get_validity_feedback(output["pred"][0], code_executor_agent)
                            if "Error" in validity_feedback:
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
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "HBD+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBD-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "QED+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "QED-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                    if logp == "LogP-":
                                        if prop == "TPSA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "TPSA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "HBD+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBD-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "QED+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "QED-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
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
            elif args.refine == "agentdrug-e":
                prop = args.data.split("/")[-1]
                ori_prompt = batch['prompt']
                max_steps = args.refine_steps + 1
                for i in range(1, max_steps + 1):
                    total_work += 1
                    output = model.inference(listize_fn(batch))
                    output["pred"] = [p.strip() if "->" not in p else p.split('->')[1].strip() for p in output["pred"]]
                    output["pred"] = [p.strip() if "becomes" not in p else p.split('becomes')[1].strip() for p in output["pred"]]
                    if i < max_steps:
                        try:
                            validity_feedback = get_validity_feedback(output["pred"][0], code_executor_agent)
                            if "Error" in validity_feedback:
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
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "HBD+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBD-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "QED+":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "QED-":
                                            hit = output_logp > input_logp + task2thres[logp][args.hit_thres][0] and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] > input_logp + task2thres[logp][args.hit_thres][0]) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                    if logp == "LogP-":
                                        if prop == "TPSA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "TPSA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a topological polar surface area (TPSA) of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a topological polar surface area (TPSA) of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "HBD+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBD-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond donors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond donors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "HBA-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and {output_prop} hydrogen bond acceptors, and the original one has a LogP value of {round(input_logp, 4)} and {input_prop} hydrogen bond acceptors. Therefore, the modified molecule is not correct."
                                        if prop == "QED+":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop > input_prop + task2thres[prop][args.hit_thres][0]
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & (test_dataset.DB["prop"] > input_prop + task2thres[prop][args.hit_thres][0])]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                        if prop == "QED-":
                                            hit = output_logp + task2thres[logp][args.hit_thres][0] < input_logp and output_prop + task2thres[prop][args.hit_thres][0] < input_prop
                                            DB = test_dataset.DB[(test_dataset.DB["logp"] + task2thres[logp][args.hit_thres][0] < input_logp) & test_dataset.DB["prop"] + task2thres[prop][args.hit_thres][0] < input_prop]
                                            property_feedback = f"The modified molecule has a LogP value of {round(output_logp, 4)} and a drug-likeness of {round(output_prop, 4)}, and the original one has a LogP value of {round(input_logp, 4)} and a drug-likeness of {round(input_prop, 4)}. Therefore, the modified molecule is not correct."
                                if hit:
                                    eval_outputs.append(output)
                                    break
                                else:
                                    try:
                                        feedback_output = "Validity:\n{}\nDesired property:\n{}".format(validity_feedback, property_feedback)
                                    except:
                                        pass
                        except:
                            continue
                        batch['prompt'] = ori_prompt + output["pred"][0] + f"\n\nImprove the modified molecule based on the following feedback:\n{feedback_output}\nRespond with only the SMILES string of your modified molecule. No explanation is needed."
                    else:
                        eval_outputs.append(output)

        progress_bar_test.update(1)

    elapsed_time = time.time() - start_time

    # Step 4: Post-processing & report
    os.makedirs(f'{args.output_dir}/inference/{args.data}', exist_ok=True)
    path = f'{args.output_dir}/inference/{args.data}/{args.model_name}_{args.llm_name}_llm_frozen{args.llm_frozen}_{args.split}_{args.refine}_refine_steps{args.refine_steps}_{args.hit_thres}.csv'
    scores = eval_funcs[args.dataset](eval_outputs, path, args.data, 
        hit_thres = args.hit_thres, 
    )
    print("Hit: {:05.2f} Hit@0.5: {:05.2f} Morgan-FTS: {:05.2f} Validity: {:05.2f} Validity check: {:05.2f} Runtime: {:05.2f}".format(
        *scores, 99.99*validity_work/total_work, elapsed_time/len(test_dataset)
    ))

if __name__ == "__main__":
    args = parse_args_llm().parse_args()
    print(f'{args.output_dir}/inference/{args.data}/{args.model_name}_{args.llm_name}_llm_frozen{args.llm_frozen}_{args.split}_{args.refine}_refine_steps{args.refine_steps}_{args.hit_thres}.csv')
    main(args)