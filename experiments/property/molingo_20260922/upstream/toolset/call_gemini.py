import google.generativeai as genai
from toolset.config import GEMINI_API_KEY, GEMINI_MODEL

# Configure API key
genai.configure(api_key=GEMINI_API_KEY)
def gemini_api(prompt: str, model: str = GEMINI_MODEL) -> str:
    """
    Calls Gemini 2.5 Flash with generateContent.
    """
    model = genai.GenerativeModel(f"models/{model}")
    
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0
        }
    )
    
    return response.text.strip()