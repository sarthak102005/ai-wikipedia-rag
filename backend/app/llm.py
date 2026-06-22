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
You are a strict Wikipedia-based QA assistant.

RULES:
- Answer ONLY using the provided context
- If answer is not in context, say: "I couldn't find that information in the article."
- Do NOT use external knowledge
- Do NOT guess
- Be precise and short

CONTEXT:
{context}

QUESTION:
{question}
"""

    response = client.chat.completions.create(
        model="openrouter/free",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1
    )

    return response.choices[0].message.content