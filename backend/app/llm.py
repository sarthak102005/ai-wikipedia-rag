"""
LLM interface — updated 4-model fallback chain.

Priority order:
  1. Groq Llama 3.3 70B (primary)   — fastest raw TPS via LPU hardware, free tier
  2. Gemini 2.5 Flash   (fallback 1) — fast, 1M context, generous free tier
  3. OpenRouter free    (fallback 2) — zero-cost fallback
  4. MiniMax-M3         (fallback 3) — 427B MoE, 1M context, instruction-focused (slowest/last resort)

Why this order?
  - Groq Llama 3.3 has the fastest speed (200-300 TPS) via LPU hardware.
  - Gemini 2.5 Flash is highly responsive, has a 1M token context window, and a free tier.
  - OpenRouter free remains the zero-cost fallback.
  - MiniMax-M3 serves as the last resort due to high capability but slower performance (18-36 TPS).

HuggingFace Spaces deployment:
  - Set MINIMAX_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY
    as Space Secrets in the HF Space settings UI.
  - load_dotenv() is a no-op when .env is absent (safe on HF Spaces).
  - All key reads use os.environ so HF secrets are picked up automatically.

Setup (local):
  Add to backend/.env:
    MINIMAX_API_KEY=<your key from https://platform.minimax.io>
    GEMINI_API_KEY=<your key from https://aistudio.google.com>
    GROQ_API_KEY=<your key from https://console.groq.com>
    OPENROUTER_API_KEY=<your key from https://openrouter.ai>
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional in deployed environments where secrets
    # are provided through environment variables instead of a local .env file.
    pass

from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError


def _get_env(key: str) -> str:
    """Read env var, stripping accidental whitespace (common copy-paste issue)."""
    return os.environ.get(key, "").strip()


# ── 1. Groq client (primary) ──────────────────────────────────────────────────
_groq_key = _get_env("GROQ_API_KEY")

_groq_client = (
    OpenAI(
        api_key=_groq_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=20.0,
    )
    if _groq_key
    else None
)

_GROQ_MODEL = "llama-3.3-70b-versatile"


# ── 2. Gemini 2.5 Flash client (fallback 1) ───────────────────────────────────
_gemini_key = _get_env("GEMINI_API_KEY")

_gemini_client = (
    OpenAI(
        api_key=_gemini_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=20.0,
    )
    if _gemini_key
    else None
)

_GEMINI_MODEL = "gemini-2.5-flash"


# ── 3. OpenRouter client (fallback 2) ─────────────────────────────────────────
_or_key = _get_env("OPENROUTER_API_KEY")

_or_client = OpenAI(
    api_key=_or_key or "no-key",   # OpenAI client requires a non-empty string
    base_url="https://openrouter.ai/api/v1",
    timeout=30.0,
)

_OR_MODEL = "openrouter/free"


# ── 4. MiniMax-M3 client (fallback 3) ─────────────────────────────────────────
_minimax_key = _get_env("MINIMAX_API_KEY")

_minimax_client = (
    OpenAI(
        api_key=_minimax_key,
        base_url="https://api.minimax.io/v1",
        timeout=45.0,
    )
    if _minimax_key
    else None
)

_MINIMAX_MODEL = "MiniMax-M3"


# ─────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────

def _build_prompt(context: str, question: str) -> str:
    return (
        "You are a Wikipedia-based QA assistant.\n"
        "Answer using ONLY the context below. Be concise.\n"
        "If the context contains tables or structured statistics, interpret them as numeric data and answer directly using those values.\n"
        'If the answer is not present, say: "I couldn\'t find that information in the article."\n\n'
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {question}"
    )


# ─────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────

def ask_llm(context: str, question: str) -> str:
    """
    Try Groq -> Gemini 2.5 Flash -> OpenRouter -> MiniMax-M3 (in that order).
    Each provider is skipped gracefully if its API key is not configured.
    """
    prompt = _build_prompt(context, question)
    messages = [{"role": "user", "content": prompt}]

    # ── Attempt 1: Groq Llama 3.3 70B ───────────────────────────────────────
    if _groq_client:
        try:
            resp = _groq_client.chat.completions.create(
                model=_GROQ_MODEL,
                messages=messages,
                temperature=0.0,
                max_tokens=512,
            )
            print(f"[llm] Answered via Groq ({_GROQ_MODEL})")
            return resp.choices[0].message.content

        except APIStatusError as e:
            if e.status_code == 429:
                print("[llm] Groq rate-limited — trying Gemini...")
            else:
                print(f"[llm] Groq error {e.status_code} — trying Gemini...")

        except (APITimeoutError, APIConnectionError) as e:
            print(f"[llm] Groq connection issue ({type(e).__name__}) — trying Gemini...")

        except Exception as e:
            print(f"[llm] Groq unexpected error: {e} — trying Gemini...")
    else:
        print("[llm] GROQ_API_KEY not set — trying Gemini...")

    # ── Attempt 2: Gemini 2.5 Flash ─────────────────────────────────────────
    if _gemini_client:
        try:
            resp = _gemini_client.chat.completions.create(
                model=_GEMINI_MODEL,
                messages=messages,
                temperature=0.0,
                max_tokens=512,
            )
            print(f"[llm] Answered via Gemini ({_GEMINI_MODEL})")
            return resp.choices[0].message.content

        except APIStatusError as e:
            if e.status_code == 429:
                print("[llm] Gemini rate-limited — trying OpenRouter...")
            else:
                print(f"[llm] Gemini error {e.status_code} — trying OpenRouter...")

        except (APITimeoutError, APIConnectionError) as e:
            print(f"[llm] Gemini connection issue ({type(e).__name__}) — trying OpenRouter...")

        except Exception as e:
            print(f"[llm] Gemini unexpected error: {e} — trying OpenRouter...")
    else:
        print("[llm] GEMINI_API_KEY not set — trying OpenRouter...")

    # ── Attempt 3: OpenRouter free ──────────────────────────────────────────
    if _or_key:
        try:
            resp = _or_client.chat.completions.create(
                model=_OR_MODEL,
                messages=messages,
                temperature=0.0,
                max_tokens=512,
            )
            print(f"[llm] Answered via OpenRouter ({_OR_MODEL})")
            return resp.choices[0].message.content

        except APIStatusError as e:
            if e.status_code == 429:
                print("[llm] OpenRouter rate-limited — trying MiniMax...")
            else:
                print(f"[llm] OpenRouter error {e.status_code} — trying MiniMax...")

        except (APITimeoutError, APIConnectionError) as e:
            print(f"[llm] OpenRouter connection issue ({type(e).__name__}) — trying MiniMax...")

        except Exception as e:
            print(f"[llm] OpenRouter unexpected error: {e} — trying MiniMax...")
    else:
        print("[llm] OPENROUTER_API_KEY not set — trying MiniMax...")

    # ── Attempt 4: MiniMax-M3 ───────────────────────────────────────────────
    if _minimax_client:
        try:
            resp = _minimax_client.chat.completions.create(
                model=_MINIMAX_MODEL,
                messages=messages,
                temperature=0.0,
                max_tokens=512,
                extra_body={"thinking": {"type": "disabled"}},
            )
            print(f"[llm] Answered via MiniMax ({_MINIMAX_MODEL})")
            return resp.choices[0].message.content

        except APITimeoutError:
            return "The AI service timed out. Please try again in a moment."

        except APIConnectionError:
            return "Could not connect to the AI service. Check your internet connection."

        except APIStatusError as e:
            return f"AI service error (HTTP {e.status_code}). Please try again later."

        except Exception as e:
            print(f"[llm] MiniMax unexpected error: {e}")
            return "An unexpected error occurred while generating the answer."
    else:
        return "All configured AI models are unavailable (API key missing or rate-limited)."