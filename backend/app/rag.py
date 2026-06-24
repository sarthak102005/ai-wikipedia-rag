"""
RAG pipeline — retrieval-augmented generation over a Wikipedia article.

v3 additions:
  - Accepts `images` list so it can semantically match a relevant image
    to the user's question and return it alongside the answer.
  - _find_related_image() embeds question + image captions and picks
    the closest match by cosine similarity (threshold 0.20).

v4 additions:
  - Accepts `tables` list (parsed Wikipedia tables) and indexes them as
    structured row-expansion + intact chunks via _make_table_chunks().
    This ensures every column header is always attached to its data cells,
    fixing retrieval for any tabular query (Test runs, ODI average, etc.).
"""

import time
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import get_embedding, get_embeddings
from app.vector_store import build_index, search, index_exists, load_index, get_total_chunks
from app.llm import ask_llm
from app.cache import cache
from app.utils import normalize_cache_key


# ─────────────────────────────────────────
# Text splitting
# ─────────────────────────────────────────

def _split_text(text: str, title: str = "") -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=150,
    )
    chunks = splitter.split_text(text)
    if title:
        prefix = f"Article: {title}\n\n"
        chunks = [prefix + chunk for chunk in chunks]
    return chunks


# ─────────────────────────────────────────
# Table → indexed chunks
# ─────────────────────────────────────────

def _make_table_chunks(tables: list[dict], title: str) -> list[str]:
    """
    Convert parsed Wikipedia tables into high-quality indexable chunks.

    Strategy — for every table we produce TWO kinds of chunks:

    1. ROW-EXPANSION (for multi-column tables, e.g. career statistics):
       Each data row becomes its own chunk where every cell is paired
       with its column header:
           Article: Virat Kohli | Career statistics
           Competition: Test | Matches: 123 | Runs scored: 9,230 | ...
       This guarantees "Test runs", "ODI batting average", etc. are each
       retrievable independently, regardless of how many rows the table has.

    2. INTACT FULL TABLE (fallback for infoboxes and general queries):
       The entire table is kept as a single Markdown chunk so that a
       broad question (e.g. "personal details") can still find it.

    For 2-column key→value infoboxes (Height, Born, etc.) we skip the
    row-expansion (it would be identical) and only keep the intact chunk.
    """
    chunks: list[str] = []
    prefix = f"Article: {title}"

    for t in tables:
        caption  = t.get("caption", "").strip()
        headers  = t.get("headers", [])
        rows     = t.get("rows",    [])

        if not rows:
            continue

        table_label = f"Table: {caption}" if caption else "Table"

        # ── Detect 2-column infobox-style tables ──────────────────────────
        is_infobox = len(headers) <= 2 and all(len(r) <= 2 for r in rows)

        if is_infobox:
            # Single intact key-value chunk
            kv_lines = [prefix, table_label]
            for row in rows:
                if len(row) == 2:
                    kv_lines.append(f"{row[0]}: {row[1]}")
                elif len(row) == 1 and row[0].strip():
                    kv_lines.append(row[0])
            chunks.append("\n".join(kv_lines))

        else:
            # ── 1. Row-expansion: one chunk per data row ──────────────────
            if headers:
                for row in rows:
                    if not any(cell.strip() for cell in row):
                        continue  # skip blank rows
                    pairs = []
                    for col_idx, cell in enumerate(row):
                        col_name = headers[col_idx] if col_idx < len(headers) else f"Column {col_idx + 1}"
                        pairs.append(f"{col_name}: {cell}")
                    row_chunk = f"{prefix} | {table_label}\n" + " | ".join(pairs)
                    chunks.append(row_chunk)

            # ── 2. Intact full table (fallback) ───────────────────────────
            md_lines = [prefix, f"{table_label}\n"]
            if headers:
                md_lines.append("| " + " | ".join(headers) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in rows:
                md_lines.append("| " + " | ".join(row) + " |")
            chunks.append("\n".join(md_lines))

    return chunks


# ─────────────────────────────────────────
# NEW: Semantic image matching
# ─────────────────────────────────────────

_IMAGE_MATCH_THRESHOLD = 0.20   # minimum cosine similarity to accept a match

def _find_related_image(question: str, images: list[dict]) -> dict | None:
    """
    Embed the question and each image's caption+filename, then return
    the image with the highest cosine similarity to the question.
    Returns None if no image passes the threshold.
    """
    if not images:
        return None
    try:
        q_emb = np.array(get_embedding(question), dtype="float32")
        norm = np.linalg.norm(q_emb)
        if norm > 0:
            q_emb /= norm

        best_score = -1.0
        best_img   = None

        for img in images:
            text = f"{img.get('caption', '')} {img.get('filename', '')}".strip()
            if not text:
                continue
            emb = np.array(get_embedding(text), dtype="float32")
            n   = np.linalg.norm(emb)
            if n > 0:
                emb /= n
            score = float(np.dot(q_emb, emb))
            if score > best_score:
                best_score = score
                best_img   = img

        if best_score >= _IMAGE_MATCH_THRESHOLD and best_img:
            return {**best_img, "match_score": round(best_score, 3)}
        return None

    except Exception as e:
        print(f"[rag] Image matching error: {e}")
        return None


# ─────────────────────────────────────────
# Main RAG entry point
# ─────────────────────────────────────────

def run_rag(
    article:  str,
    question: str,
    title:    str       = "",
    images:   list | None = None,
    tables:   list | None = None,
) -> dict:
    """
    Main RAG entry point.

    Returns:
        {
            "answer":           str,
            "sources":          [{text, score}, ...],
            "total_chunks":     int,
            "retrieved_chunks": int,
            "cache_hit":        bool,
            "time":             str,
            "related_image":    {url, caption, filename, match_score} | None,
        }
    """
    if images is None:
        images = []
    if tables is None:
        tables = []

    start_time = time.time()
    cache_key  = normalize_cache_key(f"{title}::{question}")

    # Use a versioned index key so old indexes (without table chunks) are
    # never incorrectly loaded when structured table data is available.
    index_key = f"{title}_wt" if (title and tables) else title

    # ── Cache check ──────────────────────────────────────────────────────────
    if cache_key in cache:
        result = cache[cache_key]
        sources = result.get("sources", [])
        has_new_schema = (
            "total_chunks" in result
            and isinstance(sources, list)
            and (not sources or isinstance(sources[0], dict))
        )
        if has_new_schema:
            elapsed = time.time() - start_time
            result["cache_hit"] = True
            result["time"]      = f"{elapsed:.3f} s"
            # If cached result lacks related_image, compute it now
            if "related_image" not in result and images:
                result["related_image"] = _find_related_image(question, images)
            return result
        else:
            print(f"[rag] Incompatible cache format for '{cache_key}'. Rebuilding...")

    # ── Guard: empty article ─────────────────────────────────────────────────
    if not article or not article.strip():
        elapsed = time.time() - start_time
        result = {
            "answer": "No article content was provided.",
            "sources": [], "total_chunks": 0, "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
        }
        cache[cache_key] = result
        return result

    # ── Indexing phase ───────────────────────────────────────────────────────
    try:
        if index_key and index_exists(index_key):
            load_index(index_key)
        else:
            # 1. Split prose (with title prefix for better semantic matching)
            prose_chunks = _split_text(article, title)

            # 2. Convert tables into structured, header-labeled row chunks
            table_chunks = _make_table_chunks(tables, title) if tables else []

            chunks = prose_chunks + table_chunks

            if not chunks:
                elapsed = time.time() - start_time
                result = {
                    "answer": "The article content is too short to process.",
                    "sources": [], "total_chunks": 0, "retrieved_chunks": 0,
                    "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
                }
                cache[cache_key] = result
                return result

            print(f"[rag] Indexing {len(prose_chunks)} prose + {len(table_chunks)} table chunks = {len(chunks)} total")
            embeddings = get_embeddings(chunks)
            build_index(chunks, embeddings, title=index_key)

    except Exception as e:
        print(f"[rag] Indexing error: {e}")
        elapsed = time.time() - start_time
        result = {
            "answer": "Failed to process the article. Please try again.",
            "sources": [], "total_chunks": 0, "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
        }
        cache[cache_key] = result
        return result

    # ── Retrieval phase ──────────────────────────────────────────────────────
    try:
        query_embedding = get_embedding(question)
        retrieved       = search(query_embedding, query_text=question)
    except Exception as e:
        print(f"[rag] Retrieval error: {e}")
        elapsed = time.time() - start_time
        result = {
            "answer": "Failed to search the article. Please try again.",
            "sources": [], "total_chunks": get_total_chunks(), "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
        }
        cache[cache_key] = result
        return result

    total_chunks = get_total_chunks()

    if not retrieved:
        elapsed = time.time() - start_time
        result = {
            "answer": "I couldn't find that information in the article.",
            "sources": [], "total_chunks": total_chunks, "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
        }
        cache[cache_key] = result
        return result

    # ── Generation phase ─────────────────────────────────────────────────────
    context = "\n\n".join(item["text"] for item in retrieved)
    answer  = ask_llm(context, question)

    # Semantic image matching
    related_image = _find_related_image(question, images)

    elapsed = time.time() - start_time
    result = {
        "answer":           answer,
        "sources":          retrieved,
        "total_chunks":     total_chunks,
        "retrieved_chunks": len(retrieved),
        "cache_hit":        False,
        "time":             f"{elapsed:.2f} s",
        "related_image":    related_image,
    }
    cache[cache_key] = result
    return result