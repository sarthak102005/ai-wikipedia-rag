import os
from openai import OpenAI, APIStatusError
from dotenv import load_dotenv

load_dotenv(r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\.env")

api_key = os.getenv("GEMINI_API_KEY", "").strip()
client = OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

try:
    resp = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "Say hello in one word."}],
        max_tokens=100,
    )
    print("Full response:", resp)
    print("Content:", resp.choices[0].message.content)
except Exception as e:
    print("Exception:", e)
