from source.models.llm import *

load_model = {
    'llm': BaselineLLM,
}

# Replace the following with the model paths
get_llm_path = {
    'qwen2.5-3b'      : 'Qwen/Qwen2.5-3B-Instruct'                  ,
    'qwen2.5-7b'      : 'Qwen/Qwen2.5-7B-Instruct'                  ,
    'llama-3.1-8b'    : 'meta-llama/Llama-3.1-8B-Instruct'          ,
    'llama-3.1-70b'   : 'meta-llama/Llama-3.1-70B-Instruct'         ,
}