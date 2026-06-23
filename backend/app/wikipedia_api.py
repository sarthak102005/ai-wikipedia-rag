"""
Wikipedia REST API wrapper — extended with rich content extraction.

New additions over v2:
  - _fetch_all_images(title)      : all page images (not just thumbnail) with captions
  - _fetch_tables(title)          : all article tables parsed via wikitextparser
  - _fetch_link_descriptions(title): hover-descriptions for internal Wikipedia links
  - All three run in parallel (ThreadPoolExecutor) on first fetch
  - Cache enrichment: old cached articles are enriched with new fields on next access

Cache levels (unchanged):
  1. In-memory _query_title_map  (zero cost on repeat within session)
  2. SQLite persistent cache      (survives restarts)
  3. Local article JSON store     (full disk cache)
"""

import re
import requests
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import wikitextparser as wtp
    HAS_WTP = True
except ImportError:
    HAS_WTP = False
    print("[wikipedia_api] wikitextparser not installed — table parsing disabled")

from app.article_store import get_article, save_article
from app.cache import cache

HEADERS = {"User-Agent": "AIWikipediaRAG/1.0 (sarthakmakkar60@gmail.com)"}

# In-memory query → resolved title map
_query_title_map: dict[str, str] = {}


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _clean_wikitext(text: str) -> str:
    """Strip wikitext markup, return readable plain text."""
    if not text:
        return ""
    # Remove nested templates iteratively (handles 3 levels of nesting)
    for _ in range(4):
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)
    # [[link|display]] → display,  [[link]] → link
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)
    # Remove remaining bare links / external links
    text = re.sub(r'\[+[^\]]*\]+', '', text)
    # Strip HTML tags and ref contents
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
    text = re.sub(r'<ref[^/]*/>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    # Bold / italic markup
    text = text.replace("'''", "").replace("''", "")
    # Collapse whitespace
    return ' '.join(text.split()).strip()


# ─────────────────────────────────────────
# OpenSearch — title resolution
# ─────────────────────────────────────────

def _suggest_title(query: str) -> tuple[str, bool]:
    """Resolve best-matching Wikipedia title and correct typos."""
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
# Full article text
# ─────────────────────────────────────────

def _fetch_full_article(title: str) -> str:
    """Fetch complete plain-text article body."""
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
# NEW: All page images
# ─────────────────────────────────────────

# Patterns that identify non-photo files (icons, logos, flags, etc.)
_IMG_SKIP = [
    ".svg", "icon", "logo", "flag", "commons-logo", "disambig",
    "portal", "edit-", "wikimedia", "question_mark", "red_question",
    "blank_", "padlock", "symbol", "emblem", "coat_of_arms", "stamp",
    "signature", "map_", "_map", "locator", "location",
]

def _fetch_all_images(title: str) -> list[dict]:
    """
    Fetch all real photographs / illustrations from a Wikipedia article.
    Step 1: get image filenames via prop=images
    Step 2: resolve actual URLs + captions via prop=imageinfo&extmetadata
    """
    url = "https://en.wikipedia.org/w/api.php"
    try:
        # Step 1 — list filenames
        resp = requests.get(url, params={
            "action": "query",
            "prop": "images",
            "titles": title,
            "imlimit": 60,
            "format": "json",
            "redirects": 1,
        }, headers=HEADERS, timeout=12)
        pages = resp.json().get("query", {}).get("pages", {})

        raw_titles = []
        for page in pages.values():
            for img in page.get("images", []):
                raw_titles.append(img["title"])

        if not raw_titles:
            return []

        # Filter out obvious non-photo files
        def _is_skip(t: str) -> bool:
            tl = t.lower()
            return any(p in tl for p in _IMG_SKIP)

        filtered = [t for t in raw_titles if not _is_skip(t)]
        if not filtered:
            return []

        # Step 2 — resolve URLs + captions in batches of 20
        results: list[dict] = []
        for i in range(0, min(len(filtered), 50), 20):
            batch = filtered[i : i + 20]
            resp2 = requests.get(url, params={
                "action": "query",
                "prop": "imageinfo",
                "titles": "|".join(batch),
                "iiprop": "url|extmetadata|dimensions",
                "format": "json",
            }, headers=HEADERS, timeout=15)
            pages2 = resp2.json().get("query", {}).get("pages", {})

            for page in pages2.values():
                info_list = page.get("imageinfo", [])
                if not info_list:
                    continue
                info = info_list[0]
                img_url = info.get("url", "")
                # Skip SVGs and tiny images (< 80px)
                if not img_url or img_url.lower().endswith(".svg"):
                    continue
                if info.get("width", 999) < 80 or info.get("height", 999) < 80:
                    continue

                extmeta = info.get("extmetadata", {})
                # Caption from ImageDescription (may contain HTML)
                raw_cap = extmeta.get("ImageDescription", {}).get("value", "")
                caption = re.sub(r"<[^>]+>", "", raw_cap).strip()
                filename = page.get("title", "").replace("File:", "").replace("_", " ")
                if not caption:
                    caption = filename

                results.append({
                    "url": img_url,
                    "caption": caption,
                    "filename": filename,
                })

        return results

    except Exception as e:
        print(f"[wikipedia_api] Image fetch failed: {e}")
        return []


# ─────────────────────────────────────────
# NEW: Article tables
# ─────────────────────────────────────────

def _fetch_tables(title: str) -> list[dict]:
    """
    Parse all tables from the raw wikitext using wikitextparser.
    Returns list of {caption, headers, rows} dicts.
    """
    if not HAS_WTP:
        return []

    url = "https://en.wikipedia.org/w/api.php"
    try:
        resp = requests.get(url, params={
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
            "redirects": 1,
        }, headers=HEADERS, timeout=25)

        pages = resp.json().get("query", {}).get("pages", {})
        wikitext = ""
        for page in pages.values():
            revisions = page.get("revisions", [])
            if revisions:
                slot = revisions[0].get("slots", {}).get("main", {})
                wikitext = slot.get("*", "")
                break

        if not wikitext:
            return []

        parsed = wtp.parse(wikitext)
        tables: list[dict] = []

        for table in parsed.tables:
            try:
                # span=True handles colspan/rowspan by duplicating cells
                data = table.data(span=True)
                if not data or len(data) < 2:
                    continue  # Skip empty or header-only tables

                caption_raw = table.caption or ""
                caption = _clean_wikitext(caption_raw)

                # First row as headers
                headers = [_clean_wikitext(str(c)) if c is not None else "" for c in data[0]]
                rows = [
                    [_clean_wikitext(str(c)) if c is not None else "" for c in row]
                    for row in data[1:]
                ]

                # Skip tables where all headers and first-row cells are empty
                if not any(h for h in headers) and not any(c for row in rows for c in row):
                    continue

                # Skip very large tables (> 50 rows) — likely navboxes
                if len(rows) > 50:
                    continue

                tables.append({
                    "caption": caption,
                    "headers": headers,
                    "rows": rows,
                })

            except Exception as te:
                print(f"[wikipedia_api] Table parse error: {te}")
                continue

        return tables

    except Exception as e:
        print(f"[wikipedia_api] Table fetch failed: {e}")
        return []


# ─────────────────────────────────────────
# NEW: Internal link descriptions
# ─────────────────────────────────────────

def _fetch_link_descriptions(title: str) -> dict[str, str]:
    """
    Fetch short descriptions for all internal Wikipedia links on the page.
    Returns {link_title: description_string}
    """
    url = "https://en.wikipedia.org/w/api.php"
    try:
        # Step 1 — get all links on the page (main namespace only)
        resp = requests.get(url, params={
            "action": "query",
            "prop": "links",
            "titles": title,
            "pllimit": 60,
            "plnamespace": 0,
            "format": "json",
            "redirects": 1,
        }, headers=HEADERS, timeout=12)

        pages = resp.json().get("query", {}).get("pages", {})
        link_titles: list[str] = []
        for page in pages.values():
            for link in page.get("links", []):
                link_titles.append(link["title"])

        if not link_titles:
            return {}

        link_titles = link_titles[:50]  # cap at 50

        # Step 2 — batch-fetch descriptions (20 per request)
        descriptions: dict[str, str] = {}
        for i in range(0, len(link_titles), 20):
            batch = link_titles[i : i + 20]
            resp2 = requests.get(url, params={
                "action": "query",
                "prop": "description",
                "titles": "|".join(batch),
                "format": "json",
            }, headers=HEADERS, timeout=15)

            pages2 = resp2.json().get("query", {}).get("pages", {})
            for page in pages2.values():
                t = page.get("title", "")
                desc = page.get("description", "")
                if t and desc:
                    descriptions[t] = desc

        return descriptions

    except Exception as e:
        print(f"[wikipedia_api] Link descriptions fetch failed: {e}")
        return {}


# ─────────────────────────────────────────
# Cache enrichment helper
# ─────────────────────────────────────────

def _enrich_stored(title: str, stored: dict) -> dict:
    """
    Add any new fields (images, tables, link_descriptions) missing from
    old cached articles. Fetches missing fields in parallel and re-saves.
    """
    missing = []
    if "images" not in stored:
        missing.append("images")
    if "tables" not in stored:
        missing.append("tables")
    if "link_descriptions" not in stored:
        missing.append("link_descriptions")

    if not missing:
        return stored

    fetchers = {
        "images": lambda: _fetch_all_images(title),
        "tables": lambda: _fetch_tables(title),
        "link_descriptions": lambda: _fetch_link_descriptions(title),
    }

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fetchers[k]): k for k in missing}
        for future in as_completed(futures):
            key = futures[future]
            try:
                stored[key] = future.result()
            except Exception as e:
                print(f"[wikipedia_api] Enrichment failed for {key}: {e}")
                stored[key] = [] if key != "link_descriptions" else {}

    save_article(title, stored)
    return stored


def _build_result(stored: dict, was_corrected: bool, resolved_title: str, query: str) -> dict:
    """Build the standard result dict from a stored article."""
    result = {
        "title":             stored["title"],
        "summary":           stored.get("summary", ""),
        "full_content":      stored["full_content"],
        "url":               stored.get("url", ""),
        "image":             stored.get("image"),
        "images":            stored.get("images", []),
        "tables":            stored.get("tables", []),
        "link_descriptions": stored.get("link_descriptions", {}),
    }
    if was_corrected:
        result["corrected_query"] = resolved_title
        result["original_query"]  = query
    return result


# ─────────────────────────────────────────
# Main search function
# ─────────────────────────────────────────

def search_wikipedia(query: str) -> dict:
    """
    Search Wikipedia with three-level caching + rich content extraction.
    Returns: title, summary, full_content, url, image (thumbnail),
             images (all), tables, link_descriptions.
    """
    normalized = query.strip().lower()
    db_key = f"search_query::{normalized}"

    # ── Level 1: in-memory ──────────────────────────────────────────────────
    if normalized in _query_title_map:
        cached_title = _query_title_map[normalized]
        stored = get_article(cached_title)
        if stored and stored.get("full_content"):
            print(f"[wikipedia_api] Memory cache hit: '{query}' → '{cached_title}'")
            stored = _enrich_stored(cached_title, stored)
            result = _build_result(stored, cached_title.lower() != normalized, cached_title, query)
            return result

    # ── Level 1.5: SQLite ───────────────────────────────────────────────────
    if db_key in cache:
        cached_title = cache[db_key]
        stored = get_article(cached_title)
        if stored and stored.get("full_content"):
            print(f"[wikipedia_api] SQLite cache hit: '{query}' → '{cached_title}'")
            _query_title_map[normalized] = cached_title
            stored = _enrich_stored(cached_title, stored)
            result = _build_result(stored, cached_title.lower() != normalized, cached_title, query)
            return result

    # ── Level 2: OpenSearch title resolution ────────────────────────────────
    resolved_title, was_corrected = _suggest_title(query)
    _query_title_map[normalized] = resolved_title
    cache[db_key] = resolved_title

    # ── Level 3: local article store ────────────────────────────────────────
    stored = get_article(resolved_title)
    if stored and stored.get("full_content"):
        print(f"[wikipedia_api] Disk cache hit: '{resolved_title}'")
        stored = _enrich_stored(resolved_title, stored)
        return _build_result(stored, was_corrected, resolved_title, query)

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

        # Update caches to canonical title
        _query_title_map[normalized] = title
        cache[db_key] = title

        # Fetch full article text + rich content in parallel
        full_content_fut = None
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {
                ex.submit(_fetch_full_article, title):        "full_content",
                ex.submit(_fetch_all_images, title):          "images",
                ex.submit(_fetch_tables, title):              "tables",
                ex.submit(_fetch_link_descriptions, title):   "link_descriptions",
            }
            fetch_results: dict = {}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    fetch_results[key] = future.result()
                except Exception as e:
                    print(f"[wikipedia_api] Parallel fetch failed for {key}: {e}")
                    fetch_results[key] = [] if key != "link_descriptions" else {}

        full_content = fetch_results.get("full_content") or data.get("extract", "")

        article_data = {
            "title":             title,
            "summary":           data.get("extract"),
            "full_content":      full_content,
            "url":               data.get("content_urls", {}).get("desktop", {}).get("page"),
            "image":             data.get("thumbnail", {}).get("source"),
            "images":            fetch_results.get("images", []),
            "tables":            fetch_results.get("tables", []),
            "link_descriptions": fetch_results.get("link_descriptions", {}),
        }
        save_article(title, article_data)

        result = {**article_data}
        if was_corrected:
            result["corrected_query"] = resolved_title
            result["original_query"]  = query

        return result

    except requests.Timeout:
        return {"error": "Wikipedia request timed out. Please try again."}
    except Exception as e:
        print(f"[wikipedia_api] Unexpected error: {e}")
        return {"error": "Wikipedia request failed. Please check your internet connection."}