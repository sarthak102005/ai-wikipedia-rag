"""
LLM interface — Groq (primary) + OpenRouter free (fallback).

Why Groq?
  Groq runs LLMs on custom LPU hardware — typical response in 1-3 seconds
  vs 10-30 seconds on overloaded free OpenRouter slots.
  Free tier: 6,000 tokens/minute on llama-3.1-8b-instant.

Setup:
  Add GROQ_API_KEY to backend/.env
  Get a free key at: https://console.groq.com

Fallback:
  If Groq is unavailable or not configured, falls back to openrouter/free
  (the original model that was confirmed working before).
"""

import os
from dotenv import load_dotenv
from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError

load_dotenv()

# ── Groq client (primary) ──────────────────────────────────────────────────
_groq_key = os.getenv("GROQ_API_KEY", "").strip()

_groq_client = (
    OpenAI(
        api_key=_groq_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=20.0,
    )
    if _groq_key
    else None
)

_GROQ_MODEL = "llama-3.1-8b-instant"   # fastest free model on Groq

# ── OpenRouter client (fallback) ────────────────────────────────────────────
_or_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    base_url="https://openrouter.ai/api/v1",
    timeout=30.0,
)

_OR_MODEL = "openrouter/free"           # original working model — kept as fallback


# ─────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────

def _build_prompt(context: str, question: str) -> str:
    return (
        "You are a Wikipedia-based QA assistant.\n"
        "Answer using ONLY the context below. Be concise.\n"
        'If the answer is not present, say: "I couldn\'t find that information in the article."\n\n'
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {question}"
    )


# ─────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────

def ask_llm(context: str, question: str) -> str:
    """
    Try Groq first (if GROQ_API_KEY is set), then fall back to openrouter/free.
    """
    prompt = _build_prompt(context, question)
    messages = [{"role": "user", "content": prompt}]

    # ── Attempt 1: Groq ──────────────────────────────────────────────────────
    if _groq_client:
        try:
            resp = _groq_client.chat.completions.create(
                model=_GROQ_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=512,
            )
            print(f"[llm] Answered via Groq ({_GROQ_MODEL})")
            return resp.choices[0].message.content

        except APIStatusError as e:
            if e.status_code == 429:
                print("[llm] Groq rate-limited — falling back to OpenRouter...")
            else:
                print(f"[llm] Groq error {e.status_code} — falling back to OpenRouter...")

        except (APITimeoutError, APIConnectionError) as e:
            print(f"[llm] Groq connection issue ({type(e).__name__}) — falling back...")

        except Exception as e:
            print(f"[llm] Groq unexpected error: {e} — falling back...")

    else:
        print("[llm] GROQ_API_KEY not set — using OpenRouter directly.")

    # ── Attempt 2: OpenRouter free (original fallback) ────────────────────────
    try:
        resp = _or_client.chat.completions.create(
            model=_OR_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=512,
        )
        print(f"[llm] Answered via OpenRouter ({_OR_MODEL})")
        return resp.choices[0].message.content

    except APITimeoutError:
        return "The AI service timed out. Please try again in a moment."

    except APIConnectionError:
        return "Could not connect to the AI service. Check your internet connection."

    except APIStatusError as e:
        return f"AI service error (HTTP {e.status_code}). Please try again later."

    except Exception as e:
        print(f"[llm] OpenRouter unexpected error: {e}")
        return "An unexpected error occurred while generating the answer."