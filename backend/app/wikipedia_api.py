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
from html.parser import HTMLParser


class WikiSummaryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.segments = []
        self.current_link = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            title = attrs_dict.get("title")
            if not title:
                href = attrs_dict.get("href", "")
                if href.startswith("./"):
                    title = href[2:].replace("_", " ")
            if title:
                self.current_link = title

    def handle_endtag(self, tag):
        if tag == "a":
            self.current_link = None

    def handle_data(self, data):
        if not data:
            return
        if self.current_link:
            self.segments.append({
                "text": data,
                "link": self.current_link
            })
        else:
            if self.segments and "link" not in self.segments[-1]:
                self.segments[-1]["text"] += data
            else:
                self.segments.append({
                    "text": data
                })


def parse_summary_segments(extract_html: str) -> list[dict]:
    """Parse Wikipedia summary HTML into plain text and hyperlink segments."""
    if not extract_html:
        return []
    try:
        parser = WikiSummaryParser()
        parser.feed(extract_html)
        return parser.segments
    except Exception as e:
        print(f"[wikipedia_api] Error parsing summary segments: {e}")
        return []

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("[wikipedia_api] beautifulsoup4 not installed — table parsing disabled")

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
    Parse all tables from the rendered HTML using BeautifulSoup.
    Returns list of {caption, headers, rows} dicts.
    """
    if not HAS_BS4:
        return []

    url = "https://en.wikipedia.org/w/api.php"
    try:
        resp = requests.get(url, params={
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "redirects": 1,
        }, headers=HEADERS, timeout=25)

        if resp.status_code != 200:
            return []

        html_content = resp.json().get("parse", {}).get("text", {}).get("*", "")
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        tables_list = []

        # Find all table elements
        for table in soup.find_all("table"):
            # Skip tables with 'navbox' or 'vertical-navbox' in class (likely navigation footers)
            classes = table.get("class", [])
            is_navbox = any("navbox" in str(c).lower() for c in classes)
            if is_navbox:
                continue

            caption_tag = table.find("caption")
            caption = caption_tag.text.strip() if caption_tag else ""

            # Extract rows
            rows_data = []
            for tr in table.find_all("tr"):
                cells = [cell.text.strip().replace("\xa0", " ").replace("\u2013", "-") for cell in tr.find_all(["th", "td"])]
                # Filter out empty or whitespace-only cells
                if cells:
                    rows_data.append(cells)

            if not rows_data:
                continue

            # Skip very small or empty tables
            if len(rows_data) < 2:
                continue

            # First row as headers, subsequent rows as data rows
            headers = rows_data[0]
            rows = rows_data[1:]

            # Skip huge tables (e.g., > 100 rows) as they are likely long lists of references/records
            if len(rows) > 100:
                continue

            tables_list.append({
                "caption": caption,
                "headers": headers,
                "rows": rows,
            })

        return tables_list

    except Exception as e:
        print(f"[wikipedia_api] Table fetch/parse failed: {e}")
        return []


# ─────────────────────────────────────────
# NEW: Internal link descriptions
# ─────────────────────────────────────────

def _fetch_link_descriptions(title: str, summary_links: list[str] = None) -> dict[str, dict]:
    """
    Fetch short descriptions and thumbnails for internal Wikipedia links on the page.
    Returns {link_title: {"description": desc, "thumbnail": thumb_url}}
    """
    url = "https://en.wikipedia.org/w/api.php"
    try:
        # Step 1 — get all links on the page (main namespace only)
        resp = requests.get(url, params={
            "action": "query",
            "prop": "links",
            "titles": title,
            "pllimit": 80,
            "plnamespace": 0,
            "format": "json",
            "redirects": 1,
        }, headers=HEADERS, timeout=12)

        pages = resp.json().get("query", {}).get("pages", {})
        link_titles: list[str] = []
        for page in pages.values():
            for link in page.get("links", []):
                link_titles.append(link["title"])

        # Prioritize summary links first
        if summary_links:
            seen = set()
            combined = []
            for sl in summary_links:
                if sl not in seen:
                    combined.append(sl)
                    seen.add(sl)
            for lt in link_titles:
                if lt not in seen:
                    combined.append(lt)
                    seen.add(lt)
            link_titles = combined

        if not link_titles:
            return {}

        link_titles = link_titles[:60]  # cap at 60 links

        # Step 2 — batch-fetch descriptions and thumbnails (20 per request)
        descriptions: dict[str, dict] = {}
        for i in range(0, len(link_titles), 20):
            batch = link_titles[i : i + 20]
            resp2 = requests.get(url, params={
                "action": "query",
                "prop": "description|pageimages",
                "piprop": "thumbnail",
                "pithumbsize": 160,
                "titles": "|".join(batch),
                "format": "json",
            }, headers=HEADERS, timeout=15)

            pages2 = resp2.json().get("query", {}).get("pages", {})
            for page in pages2.values():
                t = page.get("title", "")
                desc = page.get("description", "")
                thumb = page.get("thumbnail", {}).get("source")
                if t and (desc or thumb):
                    descriptions[t] = {
                        "description": desc or "No description available",
                        "thumbnail": thumb
                    }

        return descriptions

    except Exception as e:
        print(f"[wikipedia_api] Link descriptions fetch failed: {e}")
        return {}


def _fetch_disambiguation_options(title: str) -> list[dict]:
    """Fetch all link choices on a disambiguation page along with their descriptions."""
    url = "https://en.wikipedia.org/w/api.php"
    try:
        resp = requests.get(url, params={
            "action": "query",
            "prop": "links",
            "titles": title,
            "pllimit": 150,
            "plnamespace": 0,
            "format": "json",
            "redirects": 1,
        }, headers=HEADERS, timeout=12)
        
        pages = resp.json().get("query", {}).get("pages", {})
        link_titles = []
        for page in pages.values():
            for link in page.get("links", []):
                link_titles.append(link["title"])
                
        if not link_titles:
            return []
            
        options = []
        meta_keywords = {"disambiguation", "wikidata", "list of", "webarchived", "wikipedia:", "template:", "category:"}
        filtered_titles = [lt for lt in link_titles if not any(kw in lt.lower() for kw in meta_keywords)]
        
        # Batch-fetch descriptions (50 per request)
        for i in range(0, len(filtered_titles), 50):
            batch = filtered_titles[i : i + 50]
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
                if t:
                    options.append({
                        "title": t,
                        "description": desc or "No description available"
                    })
        return options
    except Exception as e:
        print(f"[wikipedia_api] Failed to fetch disambiguation options: {e}")
        return []


def _append_tables_to_content(full_content: str, tables: list[dict]) -> str:
    """Format and append tables as Markdown to the full content for RAG indexing."""
    if not tables:
        return full_content

    tables_header = "\n\n== Tables and Statistics ==\n\n"
    if tables_header in full_content:
        # Already appended
        return full_content

    table_md_blocks = []
    for t in tables:
        caption = t.get("caption", "").strip()
        headers = t.get("headers", [])
        rows = t.get("rows", [])

        md_lines = []
        if caption:
            md_lines.append(f"### Table: {caption}")
        if headers:
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            md_lines.append("| " + " | ".join(row) + " |")

        table_md_blocks.append("\n".join(md_lines))

    if table_md_blocks:
        return full_content + tables_header + "\n\n".join(table_md_blocks)
    return full_content


def _enrich_stored(title: str, stored: dict) -> dict:
    """
    Add any new fields (images, tables, link_descriptions) missing from
    old cached articles. Fetches missing fields in parallel and re-saves.
    """
    if stored.get("is_disambiguation"):
        return stored

    # 1. Fetch missing summary html and segments
    if "summary_segments" not in stored or "extract_html" not in stored:
        try:
            encoded = quote(title)
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            resp = requests.get(summary_url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                stored["extract_html"] = data.get("extract_html", "")
                stored["summary_segments"] = parse_summary_segments(stored["extract_html"])
        except Exception as e:
            print(f"[wikipedia_api] Failed to enrich summary_segments for {title}: {e}")

    # 2. Check for missing or old format link descriptions (values are string instead of dict)
    has_old_descriptions = False
    if "link_descriptions" in stored and stored["link_descriptions"]:
        first_val = next(iter(stored["link_descriptions"].values()))
        if isinstance(first_val, str):
            has_old_descriptions = True

    missing = []
    if "images" not in stored:
        missing.append("images")
    if "tables" not in stored:
        missing.append("tables")
    if "link_descriptions" not in stored or has_old_descriptions:
        missing.append("link_descriptions")

    if not missing:
        return stored

    summary_links = []
    if "summary_segments" in stored:
        summary_links = [seg["link"] for seg in stored["summary_segments"] if "link" in seg]

    fetchers = {
        "images": lambda: _fetch_all_images(title),
        "tables": lambda: _fetch_tables(title),
        "link_descriptions": lambda: _fetch_link_descriptions(title, summary_links),
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

    # Append tables to full_content if tables are present (e.g. after enrichment or from cache)
    if stored.get("tables"):
        stored["full_content"] = _append_tables_to_content(stored.get("full_content", ""), stored["tables"])

    save_article(title, stored)
    return stored


def build_segments_from_descriptions(summary: str, link_keys: list[str]) -> list[dict]:
    """Dynamically segment a summary by finding exact occurrences of key link topics."""
    if not summary or not link_keys:
        return [{"text": summary}] if summary else []
        
    sorted_keys = sorted(link_keys, key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in sorted_keys if len(k) > 2]
    if not escaped_keys:
        return [{"text": summary}]
        
    pattern = r'\b(' + '|'.join(escaped_keys) + r')\b'
    
    segments = []
    last_end = 0
    for m in re.finditer(pattern, summary, re.IGNORECASE):
        start, end = m.span()
        if start > last_end:
            segments.append({"text": summary[last_end:start]})
            
        matched_text = summary[start:end]
        canonical_key = next((k for k in sorted_keys if k.lower() == matched_text.lower()), matched_text)
        
        segments.append({
            "text": matched_text,
            "link": canonical_key
        })
        last_end = end
        
    if last_end < len(summary):
        segments.append({"text": summary[last_end:]})
        
    return segments


def _build_result(stored: dict, was_corrected: bool, resolved_title: str, query: str) -> dict:
    """Build the standard result dict from a stored article."""
    if stored.get("is_disambiguation"):
        result = {
            "is_disambiguation": True,
            "title":             stored["title"],
            "summary":           stored.get("summary", ""),
            "options":           stored.get("options", []),
            "url":               stored.get("url", ""),
        }
    else:
        summary_text = stored.get("summary", "")
        link_descs = stored.get("link_descriptions", {})
        
        # Build segments dynamically using descriptions
        summary_segments = build_segments_from_descriptions(summary_text, list(link_descs.keys()))
        
        result = {
            "title":             stored["title"],
            "summary":           summary_text,
            "extract_html":      stored.get("extract_html", ""),
            "summary_segments":  summary_segments,
            "full_content":      stored["full_content"],
            "url":               stored.get("url", ""),
            "image":             stored.get("image"),
            "images":            stored.get("images", []),
            "tables":            stored.get("tables", []),
            "link_descriptions": link_descs,
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
        if stored and (stored.get("full_content") or stored.get("is_disambiguation")):
            print(f"[wikipedia_api] Memory cache hit: '{query}' -> '{cached_title}'")
            stored = _enrich_stored(cached_title, stored)
            result = _build_result(stored, cached_title.lower() != normalized, cached_title, query)
            return result

    # ── Level 1.5: SQLite ───────────────────────────────────────────────────
    if db_key in cache:
        cached_title = cache[db_key]
        stored = get_article(cached_title)
        if stored and (stored.get("full_content") or stored.get("is_disambiguation")):
            print(f"[wikipedia_api] SQLite cache hit: '{query}' -> '{cached_title}'")
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
    if stored and (stored.get("full_content") or stored.get("is_disambiguation")):
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

        # Check for disambiguation
        if data.get("type") == "disambiguation":
            options = _fetch_disambiguation_options(title)
            article_data = {
                "is_disambiguation": True,
                "title":             title,
                "summary":           data.get("extract", "This page may refer to:"),
                "options":           options,
                "url":               data.get("content_urls", {}).get("desktop", {}).get("page"),
            }
            save_article(title, article_data)
            return _build_result(article_data, was_corrected, title, query)

        # Parse summary HTML and extract links
        extract_html = data.get("extract_html", "")
        summary_segments = parse_summary_segments(extract_html)
        summary_links = [seg["link"] for seg in summary_segments if "link" in seg]

        # Fetch full article text + rich content in parallel
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {
                ex.submit(_fetch_full_article, title):                      "full_content",
                ex.submit(_fetch_all_images, title):                        "images",
                ex.submit(_fetch_tables, title):                            "tables",
                ex.submit(_fetch_link_descriptions, title, summary_links):  "link_descriptions",
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
        tables = fetch_results.get("tables", [])
        full_content_enriched = _append_tables_to_content(full_content, tables)

        article_data = {
            "title":             title,
            "summary":           data.get("extract"),
            "extract_html":      extract_html,
            "summary_segments":  summary_segments,
            "full_content":      full_content_enriched,
            "url":               data.get("content_urls", {}).get("desktop", {}).get("page"),
            "image":             data.get("thumbnail", {}).get("source"),
            "images":            fetch_results.get("images", []),
            "tables":            tables,
            "link_descriptions": fetch_results.get("link_descriptions", {}),
        }
        save_article(title, article_data)

        return _build_result(article_data, was_corrected, title, query)

    except requests.Timeout:
        return {"error": "Wikipedia request timed out. Please try again."}
    except Exception as e:
        print(f"[wikipedia_api] Unexpected error: {e}")
        return {"error": "Wikipedia request failed. Please check your internet connection."}