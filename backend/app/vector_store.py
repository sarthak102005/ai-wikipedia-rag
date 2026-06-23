"""
FAISS vector store with persistence and cosine similarity thresholding.

Changes over original:
1. Switched from IndexFlatL2 (Euclidean) to IndexFlatIP (inner product).
   With L2-normalised vectors, inner product equals cosine similarity,
   which gives better semantic ranking for sentence embeddings.

2. Added save_index / load_index using faiss.write_index / read_index.
   Indices are stored at backend/data/faiss/<title>.index
   Chunks are stored alongside as <title>.chunks.json
   This avoids re-embedding the same article on repeat requests.

3. Added SIMILARITY_THRESHOLD: chunks scoring below the threshold are
   silently dropped. This prevents low-signal passages from confusing
   the LLM with irrelevant context.

4. index_exists(title) lets rag.py check before deciding whether to build.
"""

import faiss
import numpy as np
import json
import re
import math
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "faiss"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DIMENSION = 384

# Cosine similarity cutoff — chunks below this score are excluded from context.
# Range is [-1, 1]; 0.3 discards clearly off-topic passages while keeping
# loosely related ones that may still be useful.
SIMILARITY_THRESHOLD = 0.3

# In-memory state for the currently loaded index
_index: faiss.Index | None = None
_documents: list[str] = []


# ─────────────────────────────────────────
# File-path helpers
# ─────────────────────────────────────────

def _safe_name(title: str) -> str:
    """Convert a title to a filesystem-safe string."""
    return "".join(c if (c.isalnum() or c in " _-") else "_" for c in title).strip()


def _index_path(title: str) -> Path:
    return DATA_DIR / f"{_safe_name(title)}.index"


def _chunks_path(title: str) -> Path:
    return DATA_DIR / f"{_safe_name(title)}.chunks.json"


# ─────────────────────────────────────────
# Public API
# ─────────────────────────────────────────

def index_exists(title: str) -> bool:
    """Return True if a persisted index for this article is available."""
    return _index_path(title).exists() and _chunks_path(title).exists()


def get_total_chunks() -> int:
    """Return the total number of chunks/vectors in the active index."""
    return _index.ntotal if _index is not None else 0


def load_index(title: str) -> bool:
    """
    Load a persisted FAISS index from disk into memory.
    Returns True on success, False on any error.
    """
    global _index, _documents
    try:
        _index = faiss.read_index(str(_index_path(title)))
        with open(_chunks_path(title), "r", encoding="utf-8") as f:
            _documents = json.load(f)
        print(f"[vector_store] Loaded cached index for '{title}' ({_index.ntotal} vectors)")
        return True
    except Exception as e:
        print(f"[vector_store] Failed to load index for '{title}': {e}")
        return False


def build_index(chunks: list[str], embeddings: list, title: str = "") -> None:
    """
    Build a new FAISS index from chunks + embeddings.
    Normalises vectors for cosine similarity and optionally persists to disk.
    """
    global _index, _documents

    _documents = chunks
    vectors = np.array(embeddings, dtype="float32")

    # L2-normalise so inner product == cosine similarity
    faiss.normalize_L2(vectors)

    _index = faiss.IndexFlatIP(DIMENSION)
    _index.add(vectors)

    # Persist if a title was provided
    if title:
        try:
            faiss.write_index(_index, str(_index_path(title)))
            with open(_chunks_path(title), "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False)
            print(f"[vector_store] Saved index for '{title}' ({_index.ntotal} vectors)")
        except Exception as e:
            print(f"[vector_store] Could not persist index for '{title}': {e}")


def keyword_search(query: str, chunks: list[str], k: int = 6) -> list[dict]:
    """Simple BM25-style keyword search over in-memory chunks."""
    def tokenize(text: str) -> list[str]:
        return re.findall(r'\w+', text.lower())

    query_tokens = tokenize(query)
    stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "is", "was", "were", "be", "been", "by", "from"}
    query_tokens = [t for t in query_tokens if t not in stopwords and len(t) > 1]
    if not query_tokens:
        query_tokens = tokenize(query)
        
    if not query_tokens:
        return []

    N = len(chunks)
    if N == 0:
        return []

    idf = {}
    for token in query_tokens:
        df = sum(1 for chunk in chunks if token in chunk.lower())
        idf[token] = math.log((N - df + 0.5) / (df + 0.5) + 1.0)

    scored_chunks = []
    avg_len = sum(len(tokenize(c)) for c in chunks) / N
    k1 = 1.5
    b = 0.75

    for chunk in chunks:
        chunk_tokens = tokenize(chunk)
        chunk_len = len(chunk_tokens)
        if chunk_len == 0:
            continue
        counts = Counter(chunk_tokens)
        score = 0.0
        
        for token in query_tokens:
            if token in counts:
                tf = counts[token]
                score += idf[token] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (chunk_len / avg_len)))
        
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    
    results = []
    if scored_chunks:
        max_score = scored_chunks[0][0]
        for score, text in scored_chunks[:k]:
            # Normalize BM25 score to mock cosine similarity range [0.35, 0.7] for UI consistency
            norm_score = 0.35 + 0.35 * (score / max_score) if max_score > 0 else 0.35
            results.append({
                "text": text,
                "score": norm_score,
                "method": "keyword"
            })
    return results


def search(query_embedding: list, query_text: str = "", k: int = 6) -> list[dict]:
    """
    Return the top-k most relevant chunks using a hybrid FAISS vector
    and keyword matching search, falling back to top vector matches if none exceed threshold.
    """
    vector_results = []
    all_vector_results = []

    if _index is not None and _index.ntotal > 0:
        vector = np.array([query_embedding], dtype="float32")
        faiss.normalize_L2(vector)   # must normalise query too

        scores, indices = _index.search(vector, k)
        for score, i in zip(scores[0], indices[0]):
            if i != -1:
                item = {
                    "text": _documents[i],
                    "score": float(score),
                    "method": "vector"
                }
                all_vector_results.append(item)
                if score >= SIMILARITY_THRESHOLD:
                    vector_results.append(item)

    keyword_results = []
    if query_text and _documents:
        keyword_results = keyword_search(query_text, _documents, k=k)

    # Merge results prioritizing vector, adding unique keyword matches, sorting by score desc
    seen = set()
    merged = []
    
    for res in vector_results:
        merged.append(res)
        seen.add(res["text"])
        
    for res in keyword_results:
        if res["text"] not in seen:
            merged.append(res)
            seen.add(res["text"])
            
    merged.sort(key=lambda x: x["score"], reverse=True)
    results = merged[:k]

    # Fallback to top vector chunks regardless of threshold if we got 0 results
    if not results and all_vector_results:
        results = all_vector_results[:3]
        print(f"[vector_store] RAG Fallback: returned top {len(results)} chunks below threshold.")

    return results