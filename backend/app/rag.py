"""
RAG pipeline — retrieval-augmented generation over a Wikipedia article.

v3 additions:
  - Accepts `images` list so it can semantically match a relevant image
    to the user's question and return it alongside the answer.
  - _find_related_image() embeds question + image captions and picks
    the closest match by cosine similarity (threshold 0.20).
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

def _split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
    )
    return splitter.split_text(text)


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

def run_rag(article: str, question: str, title: str = "", images: list | None = None) -> dict:
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

    start_time = time.time()
    cache_key  = normalize_cache_key(f"{title}::{question}")

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
        if title and index_exists(title):
            load_index(title)
        else:
            chunks = _split_text(article)
            if not chunks:
                elapsed = time.time() - start_time
                result = {
                    "answer": "The article content is too short to process.",
                    "sources": [], "total_chunks": 0, "retrieved_chunks": 0,
                    "cache_hit": False, "time": f"{elapsed:.2f} s", "related_image": None,
                }
                cache[cache_key] = result
                return result
            embeddings = get_embeddings(chunks)
            build_index(chunks, embeddings, title=title)

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
        retrieved       = search(query_embedding)
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