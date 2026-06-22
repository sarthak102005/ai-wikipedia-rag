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


def search(query_embedding: list, k: int = 6) -> list[str]:
    """
    Return the top-k most relevant chunks above SIMILARITY_THRESHOLD.
    Returns an empty list if the index is uninitialised or the query
    matches nothing above the threshold.
    """
    if _index is None or _index.ntotal == 0:
        return []

    vector = np.array([query_embedding], dtype="float32")
    faiss.normalize_L2(vector)   # must normalise query too

    scores, indices = _index.search(vector, k)

    results = [
        _documents[i]
        for score, i in zip(scores[0], indices[0])
        if i != -1 and score >= SIMILARITY_THRESHOLD
    ]
    return results