from openai import OpenAI
from toolset.config import OPENAI_API_KEY, GPT_MODEL


client = OpenAI(api_key=OPENAI_API_KEY)

def gpt_api(prompt: str, model: str = GPT_MODEL) -> str:
    """
    Calls GPT with web search enabled.
    """
    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],  # enables web search
        input=prompt,
        temperature=0
    )

    return response.output_text.strip()