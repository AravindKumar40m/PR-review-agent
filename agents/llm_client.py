# agents/llm_client.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"   # or another model
# MODEL_NAME = "gemini-3-pro-preview"

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY is missing in .env file")

genai.configure(api_key=GEMINI_API_KEY)

def call_openai(prompt: str, model: str = MODEL_NAME, max_tokens: int = 512):
    """
    Unified LLM wrapper but using Gemini models.
    """
    model = genai.GenerativeModel(model)

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.0,
        )
    )

    return response.text.strip()
