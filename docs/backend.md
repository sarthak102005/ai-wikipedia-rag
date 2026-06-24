# 🐍 Backend Documentation

This document provides a detailed breakdown of every Python module in the backend, explaining its purpose, inputs, outputs, responsibilities, and how it fits into the overall system.

---

## Table of Contents

- [Module Map](#module-map)
- [main.py](#mainpy)
- [wikipedia_api.py](#wikipedia_apipy)
- [rag.py](#ragpy)
- [vector_store.py](#vector_storepy)
- [embeddings.py](#embeddingspy)
- [llm.py](#llmpy)
- [cache.py](#cachepy)
- [article_store.py](#article_storepy)
- [utils.py](#utilspy)
- [Dependency Graph](#dependency-graph)

---

## Module Map

```
backend/app/
├── main.py           ← Entry point: FastAPI app, routes, CORS
├── wikipedia_api.py  ← Wikipedia API wrapper with 3-level caching
├── rag.py            ← RAG pipeline orchestrator
├── vector_store.py   ← FAISS vector DB: build, save, load, search
├── embeddings.py     ← SentenceTransformer embedding model wrapper
├── llm.py            ← LLM client: Groq (primary) + OpenRouter (fallback)
├── cache.py          ← SQLite-backed persistent key-value cache
├── article_store.py  ← Per-article JSON persistence layer
└── utils.py          ← Cache key normalizer utility

**Purpose:** The application entry point. Defines the FastAPI app, configures CORS middleware, and declares the three API endpoints.

### Code Walkthrough

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.wikipedia_api import search_wikipedia
from app.rag import run_rag

app = FastAPI(title="AI Wikipedia RAG", version="2.0.0")
```

FastAPI is instantiated here. The `title` and `version` appear in the auto-generated `/docs` OpenAPI UI.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**CORS (Cross-Origin Resource Sharing)**: Browsers block JavaScript from calling APIs on different origins by default. Since our React app runs on `localhost:5173` and the API on `localhost:8001`, CORS middleware is required. `allow_origins` whitelists only the frontend dev server.

```python
class SearchRequest(BaseModel):
    query: str

class AskRequest(BaseModel):
    article: str       # Full article text or summary
    question: str
    title: str = ""    # Used as FAISS index key
```

Pydantic `BaseModel` automatically parses incoming JSON, validates types, and returns 422 Unprocessable Entity on invalid input — no manual validation code needed.

### Endpoints Summary

| Endpoint | Method | Handler | Description |
|---|---|---|---|
| `/` | GET | inline lambda | Health check |
| `/search` | POST | `search_wikipedia(query)` | Wikipedia article fetch |
| `/ask` | POST | `run_rag(article, question, title)` | RAG Q&A |

**Input:** HTTP request with JSON body  
**Output:** HTTP response with JSON body  
**Responsibilities:** Routing, CORS, request parsing, delegating to business logic

---

## `wikipedia_api.py`

**Purpose:** Fetches Wikipedia articles using a **3-level cache hierarchy** to minimize network calls. Handles typo correction via OpenSearch.

### Cache Levels

```
Level 1: In-memory Python dict (_query_title_map)
  └─ Hit: 0ms, no I/O
Level 1.5: SQLite cache.db
  └─ Hit: ~1ms, one SQL query
Level 2: Local JSON file (article_store)
  └─ Hit: ~2ms, one file read
Level 3: Wikipedia network calls (3 HTTP requests)
  └─ Miss: 500-1500ms
```

### Internal Functions

#### `_suggest_title(query: str) → (str, bool)`

Uses Wikipedia's **OpenSearch API** to resolve the best-matching article title and correct typos.

```python
url = "https://en.wikipedia.org/w/api.php"
params = {
    "action": "opensearch",
    "search": query,
    "limit": 1,
    "format": "json",
    "redirects": "resolve",
}
```

Returns `(resolved_title, was_different)`. If `"virat kholi"` is sent, OpenSearch returns `"Virat Kohli"` and `was_different=True`. The frontend then shows a correction banner.

#### `_fetch_full_article(title: str) → str`

Uses Wikipedia's **MediaWiki action API** with `prop=extracts&explaintext=1` to get the complete plain-text article body (not HTML). This is the text that gets chunked and embedded in the RAG pipeline.

#### `search_wikipedia(query: str) → dict`

Main entry point called by `main.py`. Implements the full 3-level cache logic and returns:

```python
{
    "title": str,
    "summary": str,          # First paragraph (Wikipedia extract)
    "full_content": str,     # Complete article (~10,000-100,000 chars)
    "url": str,
    "image": str | None,     # Thumbnail URL
    "corrected_query": str,  # Present if typo was corrected
    "original_query": str    # Present if typo was corrected
}
```

**Input:** `query: str` — user's search string  
**Output:** `dict` — article data  
**Responsibilities:** Title resolution, caching, HTTP fetching, error handling

---

## `rag.py`

**Purpose:** The RAG pipeline orchestrator. Coordinates all the steps from receiving article text and a question to returning a grounded AI answer.

### The `run_rag` Function

```python
def run_rag(article: str, question: str, title: str = "") -> dict:
```

**Returns:**
```python
{
    "answer": str,
    "sources": [{"text": str, "score": float}, ...],
    "total_chunks": int,
    "retrieved_chunks": int,
    "cache_hit": bool,
    "time": str   # e.g. "2.34 s"
}
```

### Pipeline Steps

```
Step 1: Build cache key
  normalize_cache_key(f"{title}::{question}")
  e.g. "virat kohli::when was he born"

Step 2: Check SQLite cache
  If hit → return immediately with cache_hit=True

Step 3: Guard against empty article
  If article is empty → return graceful error

Step 4: Indexing phase
  4a. If FAISS index exists on disk → load it (skip embedding)
  4b. Else:
      - Split article with RecursiveCharacterTextSplitter
        (chunk_size=500, chunk_overlap=100)
      - Embed all chunks with all-MiniLM-L6-v2
      - Build FAISS IndexFlatIP
      - Save index + chunks to disk

Step 5: Retrieval phase
  - Embed the question as query vector
  - FAISS cosine search → Top-6 chunks with score ≥ 0.30

Step 6: Generation phase
  - Join retrieved chunks into context string
  - Call ask_llm(context, question)
  - LLM is constrained to answer ONLY from context

Step 7: Cache + return
  - Store full result in SQLite
  - Return dict with answer, sources, stats
```

### Why `chunk_overlap=100`?

Imagine an article chunk ends mid-sentence:

```
...Kohli scored 183 runs in the test match held in
[CHUNK 1 ENDS]
Delhi on November 22, 2012...
[CHUNK 2 STARTS]
```

Without overlap, a question about "what happened in Delhi" might find Chunk 2 (which has "Delhi"), but the answer about the 183 runs is cut off in Chunk 1. With 100-token overlap, Chunk 2 *also contains* the end of Chunk 1, so the answer is intact.

**Input:** `article: str`, `question: str`, `title: str`  
**Output:** RAG result `dict`  
**Responsibilities:** Cache checking, chunking, embedding, retrieval, LLM calling, result caching

---

## `vector_store.py`

**Purpose:** Manages the FAISS vector database — building, saving, loading, and searching the embedding index.

### Configuration

```python
DIMENSION = 384           # Matches all-MiniLM-L6-v2 output dimension
SIMILARITY_THRESHOLD = 0.3  # Minimum cosine similarity to include a chunk
```

### Key Functions

#### `build_index(chunks, embeddings, title="")`

```python
vectors = np.array(embeddings, dtype="float32")
faiss.normalize_L2(vectors)       # In-place L2 normalization
_index = faiss.IndexFlatIP(384)   # Inner Product index
_index.add(vectors)               # Add all vectors
```

**Why L2-normalize + IndexFlatIP instead of IndexFlatL2?**

For sentence embeddings, **cosine similarity** is the standard distance metric. It measures the *angle* between two vectors rather than their absolute distance, so two texts with the same meaning but different lengths (different magnitudes) still score high similarity.

`IndexFlatL2` uses Euclidean distance, which is affected by vector magnitude. `IndexFlatIP` (inner product) equals cosine similarity *when vectors are L2-normalized* — that's why we normalize before adding to the index.

#### `search(query_embedding, k=6) → list[dict]`

```python
vector = np.array([query_embedding], dtype="float32")
faiss.normalize_L2(vector)            # Normalize query too
scores, indices = _index.search(vector, k)

results = []
for score, i in zip(scores[0], indices[0]):
    if i != -1 and score >= SIMILARITY_THRESHOLD:
        results.append({"text": _documents[i], "score": float(score)})
return results
```

The `SIMILARITY_THRESHOLD = 0.3` filters out off-topic chunks. A score of 0.3 means "30% similar" — anything lower is likely unrelated noise that would confuse the LLM.

#### `load_index(title) / save_index logic`

FAISS provides `faiss.write_index()` and `faiss.read_index()` for binary serialization. This is much faster than re-embedding: loading a pre-built index for a 50,000-character article takes ~5ms vs ~2 seconds for a fresh embedding pass.

**Input:** `chunks: list[str]`, `embeddings: list[list[float]]`, `title: str`  
**Output:** None (modifies in-memory `_index` and `_documents` globals)  
**Responsibilities:** Vector math, index management, disk persistence, similarity search

---

## `embeddings.py`

**Purpose:** A thin wrapper around the `SentenceTransformer` model. Provides `get_embedding()` (single text) and `get_embeddings()` (batch).

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def get_embedding(text: str):
    return model.encode(text).tolist()

def get_embeddings(texts):
    return model.encode(texts).tolist()
```

### Why `all-MiniLM-L6-v2`?

| Property | Value |
|---|---|
| **Output dimension** | 384 |
| **Model size** | ~22MB |
| **Inference speed** | Very fast (CPU-friendly) |
| **Quality** | Excellent semantic similarity for English |
| **License** | Apache 2.0 (free for commercial use) |

The model is downloaded from HuggingFace on first run and cached locally. Subsequent runs load it from the local cache in ~1 second.

**Note:** The module-level `model = SentenceTransformer(...)` means the model is loaded *once* when the Python process starts, not on every request. This is critical for performance.

**Input:** `str` or `list[str]`  
**Output:** `list[float]` or `list[list[float]]`  
**Responsibilities:** Text-to-vector encoding, model loading and caching

---

## `llm.py`

**Purpose:** Provides `ask_llm(context, question)` — calls the LLM with a carefully constructed prompt and returns the answer string. Implements Groq (primary) + OpenRouter (fallback) with graceful error handling.

### The Prompt

```python
def _build_prompt(context: str, question: str) -> str:
    return (
        "You are a Wikipedia-based QA assistant.\n"
        "Answer using ONLY the context below. Be concise.\n"
        'If the answer is not present, say: "I couldn\'t find that information in the article."\n\n'
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {question}"
    )
```

**Why "Answer using ONLY the context"?**

This is the core anti-hallucination instruction. Without it, the LLM might supplement Wikipedia facts with its training data, which could be outdated or wrong. By constraining the model to the retrieved context, every answer is grounded in the actual Wikipedia article text.

### LLM Configuration

| Parameter | Value | Reason |
|---|---|---|
| `temperature=0.1` | Near-zero | Factual Q&A requires deterministic, accurate answers, not creativity |
| `max_tokens=512` | ~400 words | Sufficient for a concise answer; avoids runaway generation |
| Groq timeout | 20 seconds | Fast model — if it takes >20s, something is wrong |
| OpenRouter timeout | 30 seconds | Slower free tier; more generous timeout |

### Error Handling

The function catches all error types and returns human-readable strings:

```python
except APITimeoutError:
    return "The AI service timed out. Please try again in a moment."
except APIConnectionError:
    return "Could not connect to the AI service. Check your internet connection."
except APIStatusError as e:
    return f"AI service error (HTTP {e.status_code}). Please try again later."
```

**Input:** `context: str` (joined retrieved chunks), `question: str`  
**Output:** `str` (the LLM's answer)  
**Responsibilities:** Prompt construction, LLM API calls, fallback logic, error handling

---

## `cache.py`

**Purpose:** Replaces the previous `cache = {}` Python dict with a **SQLite-backed persistent cache** that survives server restarts.

### Why SQLite?

The old in-memory dict was wiped every time the server restarted — meaning every previously asked question had to be re-processed on restart. SQLite stores answers permanently on disk.

### The `PersistentCache` Class

```python
class PersistentCache:
    def __contains__(self, key: str) -> bool: ...  # "key in cache"
    def __getitem__(self, key: str): ...            # cache["key"]
    def __setitem__(self, key: str, value): ...     # cache["key"] = value
    def get(self, key, default=None): ...           # cache.get("key", default)
```

This interface is **identical to a Python dict**, so all existing code in `rag.py` and `wikipedia_api.py` works without changes. Only the storage backend is different.

Values are serialized as JSON before storage, so complex objects (like the RAG result dict with nested lists) are stored and retrieved correctly.

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS cache (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL   -- JSON-encoded value
);
```

**File location:** `backend/data/cache.db`

**Input:** Any Python key-value pair (key must be `str`, value must be JSON-serializable)  
**Output:** Stored value on retrieval  
**Responsibilities:** SQLite connection management, JSON serialization, persistent key-value storage

---

## `article_store.py`

**Purpose:** Saves and loads full Wikipedia article data as individual JSON files in `backend/data/articles/`.

### Why One File Per Article?

An earlier design used a single `articles.json` file containing all articles. This caused issues:
- The file grew indefinitely and required full rewrites on every update
- Concurrent reads/writes could corrupt the file

With one file per article, each file is independent, reads are fast O(1) file opens, and corruption of one file never affects others.

### The Slug Function

```python
def _slug(title: str) -> str:
    cleaned = re.sub(r"[^\w\s\-]", "_", title.strip().lower())
    return re.sub(r"\s+", "_", cleaned) + ".json"
```

Examples:
- `"Virat Kohli"` → `"virat_kohli.json"`
- `"C++"` → `"c__.json"`
- `"APJ Abdul Kalam"` → `"apj_abdul_kalam.json"`

**Input:** `title: str`, `article: dict`  
**Output:** `dict | None` on load  
**Responsibilities:** File path management, JSON serialization, safe filename generation

---

## `utils.py`

**Purpose:** Provides `normalize_cache_key()` — a function that normalizes text into a stable, collision-resistant string for use as a cache key.

```python
def normalize_cache_key(text: str) -> str:
    words = text.lower().strip().split()
    cleaned = [w.strip(string.punctuation) for w in words]
    return " ".join(c if c else w for c, w in zip(cleaned, words))
```

**Why normalize?**

Without normalization, these three questions would generate three separate cache entries even though they're semantically identical:

- `"When was Virat Kohli born?"`
- `"when was virat kohli born"`
- `"When was Virat Kohli born  "` ← trailing spaces

After normalization, all three become `"when was virat kohli born"` and share one cache entry.

> ⚠️ This function is **only for cache keys**. It must never be used to modify queries sent to Wikipedia's API — the Wikipedia API needs proper casing to resolve correct article titles.

---

## Dependency Graph

```
main.py
├── wikipedia_api.py
│   ├── article_store.py
│   └── cache.py
│
└── rag.py
    ├── embeddings.py          ← SentenceTransformer
    ├── vector_store.py        ← FAISS
    ├── llm.py                 ← Groq / OpenRouter
    ├── cache.py               ← SQLite
    └── utils.py               ← normalize_cache_key
```

All modules in `app/` are imported as `from app.module import function`, which requires the server to be started from the project root with `uvicorn backend.app.main:app`.
