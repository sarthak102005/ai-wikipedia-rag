"""
FAISS vector store — cosine similarity with adaptive threshold and intro-anchor access.

Key improvements:
- get_intro_chunks(): always expose first N chunks (article intro/definition)
- Adaptive threshold in search(): if too few results, automatically lowers cutoff
- SIMILARITY_THRESHOLD lowered to 0.18 for better recall on diverse question types
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

# Cosine similarity cutoff — lowered to 0.18 for better recall.
# Adaptive search will lower this further if needed (see search()).
SIMILARITY_THRESHOLD = 0.18

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


def get_intro_chunks(n: int = 3) -> list[dict]:
    """
    Return the first N chunks from the active index (always the article introduction).
    These are used as 'anchor context' — guaranteed to include the article definition
    regardless of how well any question embeds against them.
    """
    if not _documents:
        return []
    return [
        {"text": text, "score": 0.40, "method": "intro_anchor"}
        for text in _documents[:min(n, len(_documents))]
    ]


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


def keyword_search(query: str, chunks: list[str], k: int = 8) -> list[dict]:
    """BM25-style keyword search over in-memory chunks."""
    def tokenize(text: str) -> list[str]:
        return re.findall(r'\w+', text.lower())

    query_tokens = tokenize(query)
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "is", "was", "were", "be", "been", "by", "from", "what",
        "who", "when", "where", "how", "why", "which", "did", "does", "do",
        "has", "have", "had", "are", "tell", "me", "about", "many", "much",
        "can", "could", "would", "his", "her", "its", "their", "he", "she",
    }
    filtered_tokens = [t for t in query_tokens if t not in stopwords and len(t) > 1]
    # Always keep non-stopword tokens; fallback to all tokens if none survive
    query_tokens = filtered_tokens if filtered_tokens else query_tokens

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
        chunk_lower = chunk.lower()
        chunk_tokens = tokenize(chunk)
        chunk_len = len(chunk_tokens)
        if chunk_len == 0:
            continue
        counts = Counter(chunk_tokens)
        score = 0.0

        for token in query_tokens:
            if token in counts:
                tf = counts[token]
                score += idf[token] * (tf * (k1 + 1)) / (
                    tf + k1 * (1 - b + b * (chunk_len / avg_len))
                )

        # Exact phrase bonus: if the exact query (minus punctuation) appears in the chunk, huge boost
        query_clean = re.sub(r'[^\w\s]', '', query.lower().strip())
        if query_clean and len(query_clean.split()) > 1:
            if query_clean in chunk_lower:
                score += 5.0  # Massive boost for exact phrase match
            else:
                # Try a slightly looser match (all words in order)
                pattern = r'\s+'.join(re.escape(w) for w in query_clean.split())
                if re.search(pattern, chunk_lower):
                    score += 3.0

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    results = []
    if scored_chunks:
        max_score = scored_chunks[0][0]
        for score, text in scored_chunks[:k]:
            norm_score = 0.10 + 0.25 * (score / max_score) if max_score > 0 else 0.10
            results.append({"text": text, "score": norm_score, "method": "keyword"})
    return results


def search(query_embedding: list, query_text: str = "", k: int = 10) -> list[dict]:
    """
    Hybrid FAISS vector + BM25 keyword search with adaptive threshold.

    Adaptive threshold behaviour:
      1. Try SIMILARITY_THRESHOLD (0.18)  → if >= 3 vector hits, done
      2. Drop to 0.12                     → if >= 2 vector hits, done
      3. Drop to 0.08                     → take whatever is left
      4. Absolute fallback: top-3 raw vector results regardless of score

    This ensures simple questions like "What is X?" always get relevant context
    even when the question embedding scores lower than expected against the passage.
    """
    all_vector_results = []

    if _index is not None and _index.ntotal > 0:
        vector = np.array([query_embedding], dtype="float32")
        faiss.normalize_L2(vector)

        scores, indices = _index.search(vector, min(k, _index.ntotal))
        for score, i in zip(scores[0], indices[0]):
            if i != -1:
                all_vector_results.append({
                    "text":   _documents[i],
                    "score":  float(score),
                    "method": "vector",
                })

    # Adaptive threshold — lower progressively until we have enough hits
    thresholds = [SIMILARITY_THRESHOLD, 0.12, 0.08]
    vector_results = []
    for thresh in thresholds:
        vector_results = [r for r in all_vector_results if r["score"] >= thresh]
        if len(vector_results) >= 3:
            break

    # Keyword search
    keyword_results = []
    if query_text and _documents:
        keyword_results = keyword_search(query_text, _documents, k=k)

    # Merge: vector hits first, then unique keyword hits
    seen: set[str] = set()
    merged: list[dict] = []

    for res in vector_results:
        merged.append(res)
        seen.add(res["text"])

    for res in keyword_results:
        if res["text"] not in seen:
            merged.append(res)
            seen.add(res["text"])
            if len(merged) >= k:
                break

    merged.sort(key=lambda x: x["score"], reverse=True)
    results = merged[:k]

    # Hard fallback: if still nothing, take best raw vector results
    if not results and all_vector_results:
        results = sorted(all_vector_results, key=lambda x: x["score"], reverse=True)[:3]
        print(f"[vector_store] Hard fallback: {len(results)} chunks below all thresholds.")

    return results