"""
Wikipedia REST API wrapper with two-level search caching.

Cache levels:
  1. In-memory _query_title_map  — maps normalized_query → resolved_title
     Populated on first OpenSearch call. Zero network cost on repeats.

  2. Local article store (backend/data/articles/)
     Populated on first full fetch. If the article is on disk, the REST API
     and full-article MediaWiki calls are skipped entirely.

With both levels active, the second search for the same (or similar) query
is served 100% from disk/memory — no network requests at all.

OpenSearch title resolution:
  Uses Wikipedia's opensearch API to correct typos and resolve proper nouns.
  "virat kholi" → "Virat Kohli"  /  "C++" → "C++"  /  "APJ Abdul Kalam" → handled correctly
"""

import requests
from urllib.parse import quote

from app.article_store import get_article, save_article

HEADERS = {"User-Agent": "AIWikipediaRAG/1.0 (sarthakmakkar60@gmail.com)"}

# In-memory cache: normalized_query → resolved_article_title
# Prevents repeated OpenSearch round-trips within the same server session.
_query_title_map: dict[str, str] = {}


# ─────────────────────────────────────────
# OpenSearch — title resolution
# ─────────────────────────────────────────

def _suggest_title(query: str) -> tuple[str, bool]:
    """
    Resolve the best-matching Wikipedia article title via OpenSearch.
    Returns (resolved_title, was_different).
    """
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "format": "json",
        "redirects": "resolve",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return query, False
        data = resp.json()
        titles = data[1] if len(data) > 1 else []
        if titles:
            suggested = titles[0]
            was_different = suggested.lower().strip() != query.lower().strip()
            return suggested, was_different
    except Exception as e:
        print(f"[wikipedia_api] OpenSearch failed: {e}")
    return query, False


# ─────────────────────────────────────────
# Full article text (MediaWiki action API)
# ─────────────────────────────────────────

def _fetch_full_article(title: str) -> str:
    """Fetch complete plain-text article body. Falls back to '' on error."""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "titles": title,
        "format": "json",
        "redirects": 1,
        "explaintext": 1,
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return ""
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            return page.get("extract", "")
    except Exception as e:
        print(f"[wikipedia_api] Full article fetch failed: {e}")
    return ""


# ─────────────────────────────────────────
# Main search function
# ─────────────────────────────────────────

def search_wikipedia(query: str) -> dict:
    """
    Search Wikipedia with two-level caching.

    Level 1 — In-memory query→title map:
      If this query (case-insensitive) was resolved before, the title is
      known immediately. We then check the local article store.

    Level 2 — Local article store:
      If the article is on disk, the full result is returned instantly
      without any network requests.

    First-time fetch pipeline (no cache):
      OpenSearch → REST summary → local store check → full article fetch
      → save to disk → return result
    """

    normalized = query.strip().lower()

    # ── Level 1: in-memory query cache ─────────────────────────────────────
    if normalized in _query_title_map:
        cached_title = _query_title_map[normalized]
        stored = get_article(cached_title)
        if stored and stored.get("full_content"):
            print(f"[wikipedia_api] Memory cache hit for '{query}' → '{cached_title}'")
            result = {
                "title":        stored["title"],
                "summary":      stored.get("summary", ""),
                "full_content": stored["full_content"],
                "url":          stored.get("url", ""),
                "image":        stored.get("image"),
            }
            # Re-attach correction banner metadata
            if cached_title.lower() != normalized:
                result["corrected_query"] = cached_title
                result["original_query"] = query
            return result

    # ── Level 2: OpenSearch title resolution ────────────────────────────────
    resolved_title, was_corrected = _suggest_title(query)

    # Cache this query→title mapping so future calls skip OpenSearch
    _query_title_map[normalized] = resolved_title

    # ── Level 2: local article store ────────────────────────────────────────
    stored = get_article(resolved_title)
    if stored and stored.get("full_content"):
        print(f"[wikipedia_api] Disk cache hit for '{resolved_title}'")
        result = {
            "title":        stored["title"],
            "summary":      stored.get("summary", ""),
            "full_content": stored["full_content"],
            "url":          stored.get("url", ""),
            "image":        stored.get("image"),
        }
        if was_corrected:
            result["corrected_query"] = resolved_title
            result["original_query"] = query
        return result

    # ── Full network fetch (first time only) ─────────────────────────────────
    encoded = quote(resolved_title)
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    try:
        resp = requests.get(summary_url, headers=HEADERS, timeout=10)

        if resp.status_code == 404:
            return {"error": f'No Wikipedia article found for "{resolved_title}".'}

        if resp.status_code >= 500:
            return {"error": "Wikipedia is temporarily unavailable. Please try again later."}

        if resp.status_code != 200:
            return {"error": f"Wikipedia returned an unexpected error (HTTP {resp.status_code})."}

        data = resp.json()
        title = data.get("title", resolved_title)

        # Update the cache key to the canonical title
        _query_title_map[normalized] = title

        # Fetch the full article body
        full_content = _fetch_full_article(title) or data.get("extract", "")

        # Persist to local store
        article_data = {
            "title":        title,
            "summary":      data.get("extract"),
            "full_content": full_content,
            "url":          data.get("content_urls", {}).get("desktop", {}).get("page"),
            "image":        data.get("thumbnail", {}).get("source"),
        }
        save_article(title, article_data)

        result = {
            "title":        title,
            "summary":      data.get("extract"),
            "full_content": full_content,
            "url":          data.get("content_urls", {}).get("desktop", {}).get("page"),
            "image":        data.get("thumbnail", {}).get("source"),
        }

        if was_corrected:
            result["corrected_query"] = resolved_title
            result["original_query"] = query

        return result

    except requests.Timeout:
        return {"error": "Wikipedia request timed out. Please try again."}

    except Exception as e:
        print(f"[wikipedia_api] Unexpected error: {e}")
        return {"error": "Wikipedia request failed. Please check your internet connection."}