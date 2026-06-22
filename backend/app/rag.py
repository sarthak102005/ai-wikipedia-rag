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

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import get_embedding, get_embeddings
from app.vector_store import build_index, search, index_exists, load_index
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

    Args:
        article:  Full article text (or summary if full is unavailable).
        question: User's question about the article.
        title:    Article title used as the FAISS index key on disk.

    Returns:
        {"answer": str, "sources": list[str]}
    """

    # Build a stable, collision-resistant cache key
    cache_key = normalize_cache_key(f"{title}::{question}")

    if cache_key in cache:
        return cache[cache_key]

    # Guard against empty article content
    if not article or not article.strip():
        result = {"answer": "No article content was provided.", "sources": []}
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
                result = {
                    "answer": "The article content is too short to process.",
                    "sources": [],
                }
                cache[cache_key] = result
                return result

            embeddings = get_embeddings(chunks)
            build_index(chunks, embeddings, title=title)

    except Exception as e:
        print(f"[rag] Indexing error: {e}")
        result = {
            "answer": "Failed to process the article. Please try again.",
            "sources": [],
        }
        cache[cache_key] = result
        return result

    # ── Retrieval phase ─────────────────────────────────────────────────────
    try:
        query_embedding = get_embedding(question)
        retrieved = search(query_embedding)
    except Exception as e:
        print(f"[rag] Retrieval error: {e}")
        result = {
            "answer": "Failed to search the article. Please try again.",
            "sources": [],
        }
        cache[cache_key] = result
        return result

    if not retrieved:
        result = {
            "answer": "I couldn't find that information in the article.",
            "sources": [],
        }
        cache[cache_key] = result
        return result

    # ── Generation phase ────────────────────────────────────────────────────
    context = "\n\n".join(retrieved)
    answer = ask_llm(context, question)

    result = {"answer": answer, "sources": retrieved}
    cache[cache_key] = result
    return result