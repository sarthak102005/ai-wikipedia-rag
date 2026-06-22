"""
RAG pipeline — retrieval-augmented generation over a Wikipedia article.

Changes over original:
1. Cache key uses normalize_cache_key(title + question) so slight spacing
   differences in the same question still hit the cache.
   The title prefix ensures questions about different articles don't collide.

2. Persistent FAISS: if an index already exists on disk for this article,
   it is loaded instead of re-embedding (huge speed improvement on repeats).

3. build_index is now called with `title` so the index is saved after the
   first embedding pass.

4. Both indexing and retrieval are wrapped in individual try/except blocks
   with user-friendly error messages instead of crashing the endpoint.
"""

import time
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import get_embedding, get_embeddings
from app.vector_store import build_index, search, index_exists, load_index, get_total_chunks
from app.llm import ask_llm
from app.cache import cache
from app.utils import normalize_cache_key


def _split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
    )
    return splitter.split_text(text)


def run_rag(article: str, question: str, title: str = "") -> dict:
    """
    Main RAG entry point.

    Returns enriched payload:
        {
            "answer": str,
            "sources": [{"text": str, "score": float}, ...],
            "total_chunks": int,
            "retrieved_chunks": int,
            "cache_hit": bool,
            "time": str
        }
    """
    start_time = time.time()

    # Build a stable, collision-resistant cache key
    cache_key = normalize_cache_key(f"{title}::{question}")

    # Check cache hit
    if cache_key in cache:
        result = cache[cache_key]
        # Validate schema of cached result
        sources = result.get("sources", [])
        has_new_schema = (
            "total_chunks" in result and
            isinstance(sources, list) and
            (len(sources) == 0 or isinstance(sources[0], dict))
        )
        if has_new_schema:
            # Dynamically calculate response time for the cache retrieval
            elapsed = time.time() - start_time
            result["cache_hit"] = True
            result["time"] = f"{elapsed:.3f} s"
            return result
        else:
            print(f"[rag] Incompatible cache format for '{cache_key}'. Rebuilding...")

    # Guard against empty article content
    if not article or not article.strip():
        elapsed = time.time() - start_time
        result = {
            "answer": "No article content was provided.",
            "sources": [],
            "total_chunks": 0,
            "retrieved_chunks": 0,
            "cache_hit": False,
            "time": f"{elapsed:.2f} s"
        }
        cache[cache_key] = result
        return result

    # ── Indexing phase ──────────────────────────────────────────────────────
    try:
        if title and index_exists(title):
            # Reuse persisted index — skip embedding entirely
            loaded = load_index(title)
        else:
            loaded = False

        if not loaded:
            chunks = _split_text(article)

            if not chunks:
                elapsed = time.time() - start_time
                result = {
                    "answer": "The article content is too short to process.",
                    "sources": [],
                    "total_chunks": 0,
                    "retrieved_chunks": 0,
                    "cache_hit": False,
                    "time": f"{elapsed:.2f} s"
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
            "sources": [],
            "total_chunks": 0,
            "retrieved_chunks": 0,
            "cache_hit": False,
            "time": f"{elapsed:.2f} s"
        }
        cache[cache_key] = result
        return result

    # ── Retrieval phase ─────────────────────────────────────────────────────
    try:
        query_embedding = get_embedding(question)
        retrieved = search(query_embedding)
    except Exception as e:
        print(f"[rag] Retrieval error: {e}")
        elapsed = time.time() - start_time
        result = {
            "answer": "Failed to search the article. Please try again.",
            "sources": [],
            "total_chunks": get_total_chunks(),
            "retrieved_chunks": 0,
            "cache_hit": False,
            "time": f"{elapsed:.2f} s"
        }
        cache[cache_key] = result
        return result

    total_chunks = get_total_chunks()

    if not retrieved:
        elapsed = time.time() - start_time
        result = {
            "answer": "I couldn't find that information in the article.",
            "sources": [],
            "total_chunks": total_chunks,
            "retrieved_chunks": 0,
            "cache_hit": False,
            "time": f"{elapsed:.2f} s"
        }
        cache[cache_key] = result
        return result

    # ── Generation phase ────────────────────────────────────────────────────
    # Extract text from the list of similarity-score dicts
    context_chunks = [item["text"] for item in retrieved]
    context = "\n\n".join(context_chunks)
    answer = ask_llm(context, question)

    elapsed = time.time() - start_time
    result = {
        "answer": answer,
        "sources": retrieved,  # list of dicts with text and score
        "total_chunks": total_chunks,
        "retrieved_chunks": len(retrieved),
        "cache_hit": False,
        "time": f"{elapsed:.2f} s"
    }
    cache[cache_key] = result
    return result