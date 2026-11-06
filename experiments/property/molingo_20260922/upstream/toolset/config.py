import torch
OPENAI_API_KEY = '' #YOUR OPENAI API KEY
GPT_MODEL = "gpt-5.4" #4.1
GEMINI_API_KEY = '' #YOUR GEMINI API KEY
GEMINI_MODEL = "gemini-pro-latest" #gemini-flash-latest", "2.5-flash"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")