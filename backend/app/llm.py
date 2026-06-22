import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


def ask_llm(context: str, question: str):

    prompt = f"""
You are a helpful AI assistant.

Answer ONLY from the context below.

If the answer is not present, say:
"I couldn't find that information in the article."

Context:
{context}

Question:
{question}
"""

    response = client.chat.completions.create(
        model="openrouter/free",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return response.choices[0].message.content