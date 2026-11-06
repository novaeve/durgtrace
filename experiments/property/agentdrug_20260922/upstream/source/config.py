import argparse

def parse_args_llm():
    parser = argparse.ArgumentParser(description="AgentDrug")
    parser.add_argument("--project", type=str, default="AgentDrug")
    parser.add_argument("--seed", type=int, default=0)

    # Model related
    parser.add_argument("--model_name", type=str, default='llm')
    parser.add_argument("--llm_name", type=str)
    parser.add_argument("--llm_frozen", type=str, default='True')
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--n_gpus", type=int, default=2)

    # Model Training
    parser.add_argument("--dataset", type=str, default='generation')
    parser.add_argument("--path", type=str, default='../AgentDrug-datasets')
    parser.add_argument("--data", type=str)
    parser.add_argument("--split", type=str, default="train")
    parser.add_argument("--hit_thres", type=int)
    parser.add_argument("--max_prompt_length", type=int, default=256)

    # Inference
    parser.add_argument("--max_completion_length", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--refine", type=str, default="None")
    parser.add_argument("--refine_steps", type=int)
    parser.add_argument("--DB_size", type=int, default=10000)

    # Checkpoint
    parser.add_argument("--run_name", type=str, default='')
    parser.add_argument("--output_dir", type=str, default='output')
    parser.add_argument("--checkpoint_path", type=str, default=None)

    return parser