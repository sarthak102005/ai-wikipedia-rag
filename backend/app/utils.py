"""
Utility helpers for the RAG pipeline.

IMPORTANT: normalize_cache_key is ONLY for cache lookups.
           Never pass its output to the Wikipedia REST API.
"""


import string


def normalize_cache_key(text: str) -> str:
    """
    Normalize text for use as a cache key.
    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse multiple spaces into one
    - Strip common punctuation (e.g., "?", "!", ".") from words to avoid punctuation cache misses

    Do NOT use this for Wikipedia API calls — it must never strip
    punctuation or alter queries used for external lookups.
    """
    words = text.lower().strip().split()
    cleaned = []
    for w in words:
        cw = w.strip(string.punctuation)
        cleaned.append(cw if cw else w)
    return " ".join(cleaned)
