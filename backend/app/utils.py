"""
Utility helpers for the RAG pipeline.

IMPORTANT: normalize_cache_key is ONLY for cache lookups.
           Never pass its output to the Wikipedia REST API.
"""


def normalize_cache_key(text: str) -> str:
    """
    Normalize text for use as a cache key.
    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse multiple spaces into one

    Do NOT use this for Wikipedia API calls — it must never strip
    punctuation or alter queries used for external lookups.
    """
    return " ".join(text.lower().strip().split())
