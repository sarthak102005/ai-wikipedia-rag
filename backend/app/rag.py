"""
RAG pipeline — retrieval-augmented generation over a Wikipedia article.

Key improvements in this version:
  - CHUNK_VERSION constant: any change to chunk_size/overlap automatically invalidates
    cached FAISS indexes so stale indexes can never silently corrupt results.
  - Multi-query retrieval: every question is searched with 2-4 reformulations
    (original, title-augmented, declarative, keyword-only). Results are merged
    and deduplicated by best score — dramatically improves recall for both simple
    ("What is X?") and complex multi-hop questions.
  - Intro anchor chunks: the first 3 chunks (article definition/intro) are ALWAYS
    included in context regardless of similarity score. This guarantees "What is X?"
    / "Who is X?" always sees the answer.
  - Context separator: chunks joined with "\n\n---\n\n" so the LLM clearly sees
    chunk boundaries and doesn't conflate unrelated passages.
  - Cache key includes CHUNK_VERSION so param changes don't serve stale answers.
"""

import time
import re
import hashlib
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import get_embedding, get_embeddings
from app.vector_store import (
    build_index, search, index_exists, load_index,
    get_total_chunks, get_intro_chunks,
)
from app.llm import ask_llm
from app.cache import cache
from app.utils import normalize_cache_key


# ─────────────────────────────────────────
# Chunk versioning — CRITICAL
# ─────────────────────────────────────────
# Bump this string whenever chunk_size, chunk_overlap, or separators change.
# It is embedded in the FAISS index key so old on-disk indexes are never loaded
# after a param change — they are simply rebuilt fresh.
CHUNK_VERSION = "v5_c600_o200"


# ─────────────────────────────────────────
# Text splitting
# ─────────────────────────────────────────

def _split_text(text: str, title: str = "") -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
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
            kv_lines = [prefix, table_label]
            for row in rows:
                if len(row) == 2:
                    kv_lines.append(f"{row[0]}: {row[1]}")
                elif len(row) == 1 and row[0].strip():
                    kv_lines.append(row[0])
            chunks.append("\n".join(kv_lines))

        else:
            # ── 1. Row-expansion ──────────────────────────────────────────
            if headers:
                for row in rows:
                    if not any(cell.strip() for cell in row):
                        continue
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
# Semantic image matching
# ─────────────────────────────────────────

_IMAGE_MATCH_THRESHOLD = 0.20

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
# Multi-query retrieval
# ─────────────────────────────────────────

def _augment_queries(question: str, title: str) -> list[str]:
    """
    Generate 2-5 query reformulations to maximise retrieval coverage.

    Rationale: all-MiniLM-L6-v2 is a general sentence-similarity model, not a
    dedicated question-passage retrieval model. A question like "What is Mount
    Everest?" may embed further from the intro paragraph than expected.
    By also searching with the title name alone, "Mount Everest is", and the
    title+question, we dramatically increase the chance of finding the right chunks.
    """
    queries = [question]
    q_lower = question.lower().strip("?. ")

    if title:
        # Title-augmented — moves the embedding closer to the article domain
        queries.append(f"{title}: {question}")

        # Declarative rewrite for definition questions
        is_definition_q = any(q_lower.startswith(p) for p in [
            "what is", "what are", "who is", "who was", "who are",
            "tell me about", "describe", "explain",
        ])
        if is_definition_q:
            queries.append(title)                    # title alone → matches intro well
            queries.append(f"{title} is")            # declarative form

        # Temporal / date questions
        elif any(q_lower.startswith(p) for p in ["when was", "when did", "when is", "what year"]):
            queries.append(f"{title} date year founded born")

        # Numeric / statistical questions
        elif any(w in q_lower for w in ["how many", "how much", "how tall", "how high",
                                         "height", "elevation", "altitude", "population",
                                         "score", "runs", "average", "record"]):
            queries.append(f"{title} statistics numbers data")

        # Causal / reason questions
        elif any(q_lower.startswith(p) for p in ["why", "what caused", "reason"]):
            queries.append(f"{title} cause reason why")

        # Location questions
        elif any(q_lower.startswith(p) for p in ["where", "location", "situated"]):
            queries.append(f"{title} location situated country")

    # Remove exact duplicates while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def _multi_retrieve(question: str, title: str, k: int = 10) -> list[dict]:
    """
    Retrieve using multiple query formulations, merge by best score per chunk.

    Returns a deduplicated list sorted by descending similarity score.
    """
    queries = _augment_queries(question, title)
    best_by_text: dict[str, dict] = {}

    for query_str in queries:
        try:
            emb = get_embedding(query_str)
            results = search(emb, query_text=query_str, k=k)
            for r in results:
                text = r["text"]
                if text not in best_by_text or r["score"] > best_by_text[text]["score"]:
                    best_by_text[text] = r
        except Exception as e:
            print(f"[rag] Multi-query error for '{query_str[:60]}': {e}")

    return sorted(best_by_text.values(), key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────
# Direct answer extraction (stats / tables)
# ─────────────────────────────────────────

def _extract_direct_answer(question: str, retrieved: list[dict]) -> str | None:
    q = question.lower()
    if not retrieved:
        return None

    # Spouse / relations questions
    if any(keyword in q for keyword in ["spouse", "wife", "married", "husband", "wife's", "spouse's"]):
        for item in retrieved:
            text = item["text"]
            for line in text.splitlines():
                if any(key in line.lower() for key in ["relations", "spouse", "wife", "married"]):
                    line = line.strip()
                    if not line:
                        continue
                    if "|" in line:
                        parts = [p.strip() for p in line.split("|") if p.strip()]
                        candidate = next((p for p in parts if not any(
                            k in p.lower() for k in ["relations", "spouse", "wife", "married"]
                        )), None)
                        if candidate:
                            return f"The article lists his relations/spouse as: {candidate}."
                    if ":" in line:
                        return f"The article lists his relations/spouse as: {line.split(':', 1)[1].strip()}."
                    return f"The article lists: {line}."

    # Runs questions
    if "run" in q:
        for item in retrieved:
            text = item["text"]
            if "runs scored" not in text.lower():
                continue

            match = re.search(
                r"Runs scored\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)",
                text, flags=re.IGNORECASE,
            )
            if match:
                return (
                    f"According to the article, he has scored {match.group(1)} Test runs, "
                    f"{match.group(2)} ODI runs, {match.group(3)} T20I runs, and {match.group(4)} FC runs."
                )

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for idx, line in enumerate(lines):
                if "runs scored" in line.lower():
                    values = []
                    for j in range(idx + 1, min(idx + 6, len(lines))):
                        if re.fullmatch(r"[\d,]+", lines[j]):
                            values.append(lines[j])
                    if len(values) >= 4:
                        return (
                            f"According to the article, he has scored {values[0]} Test runs, "
                            f"{values[1]} ODI runs, {values[2]} T20I runs, and {values[3]} FC runs."
                        )
                    if values:
                        return f"According to the article, he has scored {' / '.join(values)} runs."

    return None


def _compute_confidence_score(retrieved: list[dict]) -> float:
    """Compute a local confidence score from retrieved chunk signals only."""
    if not retrieved:
        return 0.0

    # Only count non-anchor chunks for the score
    scored = [r for r in retrieved if r.get("method") != "intro_anchor"]
    if not scored:
        scored = retrieved

    scores = [max(0.0, float(item.get("score", 0.0))) for item in scored]
    top_score = max(scores)
    avg_score = sum(scores) / len(scores)
    count_factor = min(len(scores), 8) / 8.0

    confidence = 0.6 * top_score + 0.25 * avg_score + 0.15 * count_factor
    if top_score < 0.35:
        confidence *= 0.9

    return round(min(1.0, max(0.0, confidence)), 3)


# ─────────────────────────────────────────
# Main RAG entry point
# ─────────────────────────────────────────

def run_rag(
    article:  str,
    question: str,
    title:    str       = "",
    images:   list | None = None,
    tables:   list | None = None,
    conversation_history: list[dict] | None = None,
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

    # Cache key includes CHUNK_VERSION so param changes invalidate old entries.
    # Conversation history is hashed in so different sessions don't collide.
    conv_hash = ""
    if conversation_history:
        conv_str = str([(e.get("question", ""), e.get("answer", "")) for e in conversation_history[-6:]])
        conv_hash = "_" + hashlib.md5(conv_str.encode()).hexdigest()[:8]

    cache_key = normalize_cache_key(f"{CHUNK_VERSION}::{title}::{question}{conv_hash}")

    # FAISS index key includes CHUNK_VERSION — prevents loading stale indexes
    # built with different chunk params.
    index_key = f"{title}_{CHUNK_VERSION}" + ("_wt" if (title and tables) else "")

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
            if "confidence_score" not in result:
                result["confidence_score"] = _compute_confidence_score(sources)
            if "related_image" not in result and images:
                result["related_image"] = _find_related_image(question, images)
            return result

    # ── Guard: empty article ─────────────────────────────────────────────────
    if not article or not article.strip():
        elapsed = time.time() - start_time
        result = {
            "answer": "No article content was provided.",
            "sources": [], "total_chunks": 0, "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
            "confidence_score": 0.0,
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
                    "confidence_score": 0.0,
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
            "confidence_score": 0.0,
        }
        cache[cache_key] = result
        return result

    # ── Retrieval phase ──────────────────────────────────────────────────────
    try:
        # Multi-query retrieval: search with question + title-augmented reformulations
        retrieved = _multi_retrieve(question, title, k=10)

    except Exception as e:
        print(f"[rag] Retrieval error: {e}")
        elapsed = time.time() - start_time
        result = {
            "answer": "Failed to search the article. Please try again.",
            "sources": [], "total_chunks": get_total_chunks(), "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
            "confidence_score": 0.0,
        }
        cache[cache_key] = result
        return result

    total_chunks = get_total_chunks()

    # ── Anchor chunks — always include article intro in context ──────────────
    # The first 3 chunks contain the article definition/introduction.
    # These guarantee "What is X?" / "Who is X?" always finds the answer
    # even when the question embedding scores low against the intro passage.
    intro_chunks = get_intro_chunks(n=3)
    retrieved_texts = {r["text"] for r in retrieved}
    for chunk in intro_chunks:
        if chunk["text"] not in retrieved_texts:
            chunk["score"] = 100.0  # Force it to the top
            retrieved.append(chunk)
            retrieved_texts.add(chunk["text"])
        else:
            # If already retrieved, boost its score
            for r in retrieved:
                if r["text"] == chunk["text"]:
                    r["score"] = 100.0

    # Re-sort after merging: semantic hits first, anchor chunks at bottom
    # (so LLM sees highest-relevance context first)
    retrieved.sort(key=lambda x: x["score"], reverse=True)

    if not retrieved:
        elapsed = time.time() - start_time
        result = {
            "answer": "I couldn't find that information in the article.",
            "sources": [], "total_chunks": total_chunks, "retrieved_chunks": 0,
            "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
            "confidence_score": 0.0,
        }
        cache[cache_key] = result
        return result

    # Cap to 12 candidates; direct-answer extractor uses all of them
    retrieved = retrieved[:12]

    # ── Direct answer extraction (stats / tables) ────────────────────────────
    direct_answer = _extract_direct_answer(question, retrieved)

    if direct_answer is not None:
        answer = direct_answer
    else:
        # Use top-8 chunks for LLM context; separator makes chunk boundaries clear
        context_chunks = retrieved[:8]
        context = "\n\n---\n\n".join(item["text"] for item in context_chunks)
        answer = ask_llm(context, question, conversation_history=conversation_history)

    # Semantic image matching
    related_image = _find_related_image(question, images)

    elapsed = time.time() - start_time
    confidence_score = _compute_confidence_score(retrieved)
    result = {
        "answer":           answer,
        "sources":          retrieved,
        "total_chunks":     total_chunks,
        "retrieved_chunks": len(retrieved),
        "cache_hit":        False,
        "time":             f"{elapsed:.2f} s",
        "related_image":    related_image,
        "confidence_score": confidence_score,
    }
    cache[cache_key] = result
    return result