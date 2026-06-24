# 🔬 RAG Pipeline — Complete Explanation

This document explains **Retrieval-Augmented Generation (RAG)** from first principles. It is written for beginners but includes the technical depth that software engineers and researchers expect.

---

## Table of Contents

- [What is RAG?](#what-is-rag)
- [The Problem RAG Solves](#the-problem-rag-solves)
- [Why Not Send the Whole Article?](#why-not-send-the-whole-article)
- [The Pipeline Step by Step](#the-pipeline-step-by-step)
- [Step 1 — Chunking](#step-1--chunking)
- [Step 2 — Embeddings](#step-2--embeddings)
- [Step 3 — FAISS Vector Index](#step-3--faiss-vector-index)
- [Step 4 — Retrieval (Similarity Search)](#step-4--retrieval-similarity-search)
- [Step 5 — Generation (The LLM)](#step-5--generation-the-llm)
- [How Hallucination is Reduced](#how-hallucination-is-reduced)
- [Cache Hit vs Cache Miss](#cache-hit-vs-cache-miss)
- [Why FAISS?](#why-faiss)
- [Performance Analysis](#performance-analysis)
- [Visual Summary](#visual-summary)

---

## What is RAG?

**Retrieval-Augmented Generation (RAG)** is a technique that combines two things:

1. **Retrieval** — Finding the most relevant information from a knowledge base (like Wikipedia)
2. **Generation** — Using an AI language model (LLM) to write an answer based on that information

Think of it like an **open-book exam**:
- Without RAG, the LLM answers from memory (what it learned during training) — like a closed-book exam. It might "hallucinate" or make up facts.
- With RAG, the LLM is given the relevant pages to reference before answering — like an open-book exam. The answer is grounded in real facts.

---

## The Problem RAG Solves

Large Language Models (LLMs) like GPT-4, Llama, and Gemini are trained on massive amounts of internet text. They're incredibly knowledgeable, but they have fundamental limitations:

| Problem | Description |
|---|---|
| **Hallucination** | LLMs sometimes fabricate facts with high confidence |
| **Knowledge cutoff** | Training data has a cutoff date; newer events are unknown |
| **No source attribution** | LLMs can't cite where they got information from |
| **Context length limits** | LLMs can only read a limited number of tokens at once |
| **Topic depth** | Wikipedia articles go far deeper than training data sampling |

RAG solves all of these by **grounding the LLM in a retrieved document** instead of relying on its parametric memory.

---

## Why Not Send the Whole Article?

This is the most common question beginners ask. "If I have the full Wikipedia article, why not just send all of it to the LLM?"

### Reason 1: Token Limits

LLMs have **context window limits** — the maximum amount of text they can process at once. GPT-4 Turbo allows ~128,000 tokens (~100,000 words). Llama 3.1 8B allows 8,192 tokens (~6,000 words).

A detailed Wikipedia article on "Black holes" is ~12,000 words. That **exceeds** the token limit for many models.

### Reason 2: Cost

With cloud LLM APIs, you pay per token (input + output). Sending 10,000 words of article context for every question would cost significantly more than sending 500 words of retrieved context.

### Reason 3: Quality — "Lost in the Middle"

Research shows that LLMs perform **worse** when the relevant information is buried in a large document. If you send a 10,000-word article and the answer is in paragraph 47, the LLM may miss or misprocess it.

> **"Lost in the Middle"** — Liu et al., 2024: LLMs are significantly better at using information at the beginning or end of a long context. Information in the middle is often ignored.

By retrieving only the **most relevant chunks**, we put the answer at the top of the context where the LLM reads most reliably.

### Reason 4: Speed

Processing 10,000 tokens takes longer than 500 tokens. Retrieval makes responses faster.

---

## The Pipeline Step by Step

Here's the complete RAG pipeline as implemented in this project:

```
Wikipedia Article (raw text, ~10,000-80,000 characters)
    │
    ▼  STEP 1: CHUNKING
Split into overlapping chunks
(chunk_size=500 tokens, chunk_overlap=100 tokens)
    │
    ▼  STEP 2: EMBEDDINGS
Convert each chunk to a 384-dimensional vector
using all-MiniLM-L6-v2 (SentenceTransformer)
    │
    ▼  STEP 3: FAISS INDEX
Store all vectors in FAISS IndexFlatIP
(Inner product = cosine similarity after L2 normalization)
    │
    ▼  STEP 4: RETRIEVAL
Embed the user's question as a query vector
Cosine similarity search → Top-6 chunks with score ≥ 0.30
    │
    ▼  STEP 5: GENERATION
Join retrieved chunks into a context string
Send to LLM with strict prompt: "Answer ONLY from context"
    │
    ▼  OUTPUT
{
  answer: "...",
  sources: [{text: "...", score: 0.87}, ...],
  total_chunks: 42,
  retrieved_chunks: 4,
  time: "2.34 s"
}
```

---

## Step 1 — Chunking

### What is Chunking?

Chunking is the process of splitting a long document into smaller, overlapping pieces called **chunks**.

```
Article: "Virat Kohli (born 5 November 1988) is an Indian cricketer who
          currently captains the Royal Challengers Bengaluru in the IPL.
          He is widely regarded as one of the greatest batters of all time...
          [8000 more words...]"

After chunking (500 tokens each):
Chunk 1: "Virat Kohli (born 5 November 1988) is an Indian cricketer who
          currently captains the Royal Challengers..."
Chunk 2: "...regarded as one of the greatest batters of all time. He holds
          many batting records..."
Chunk 3: "...Early life: Kohli was born in Delhi and showed interest in
          cricket from a young age..."
[... 40 more chunks]
```

### Why `RecursiveCharacterTextSplitter`?

LangChain's `RecursiveCharacterTextSplitter` is smarter than a naive character splitter. It tries to break text at natural boundaries **in order of preference**:

1. `\n\n` (paragraph break)
2. `\n` (line break)
3. ` ` (word boundary)
4. `""` (character boundary — last resort)

This means chunks end at paragraph or sentence boundaries whenever possible, preserving semantic coherence.

### Why `chunk_overlap=100`?

Imagine the answer spans two consecutive chunks:

```
Chunk 7 ends:    "...He scored 183 runs in the test match held in"
Chunk 8 starts:  "Delhi on 22 November 2012, which set a record..."
```

Without overlap, FAISS would find Chunk 8 (has "Delhi") or Chunk 7 (has "183 runs"), but neither chunk alone has the complete answer.

With 100-token overlap, Chunk 8 **includes the last 100 tokens of Chunk 7**, so the complete answer is present in a single chunk:

```
Chunk 8 (with overlap): "...He scored 183 runs in the test match held in
                         Delhi on 22 November 2012, which set a record..."
```

**Rule of thumb:** Chunk overlap should be 10-20% of chunk size. At `chunk_size=500, chunk_overlap=100`, the overlap is 20%.

---

## Step 2 — Embeddings

### What is an Embedding?

An **embedding** is a list of numbers that represents the *meaning* of a piece of text. Two pieces of text with similar meanings will have similar embeddings — they'll be close together in the mathematical space.

```
"Virat Kohli was born in Delhi"
→ [0.234, -0.891, 0.102, 0.567, ..., -0.334]  # 384 numbers

"Kohli's birthplace is Delhi, India"  
→ [0.241, -0.875, 0.098, 0.559, ..., -0.321]  # Similar numbers!

"Black holes warp spacetime"
→ [-0.712, 0.334, -0.567, 0.891, ..., 0.102]  # Very different numbers
```

The model `all-MiniLM-L6-v2` produces **384-dimensional vectors**. Each number captures a different "semantic feature" of the text.

### Why `all-MiniLM-L6-v2`?

This model is the gold standard for lightweight semantic embeddings:

| Metric | Value |
|---|---|
| **Parameters** | 22.7 million |
| **Embedding dimension** | 384 |
| **Model size** | ~22 MB |
| **Speed** | ~14,000 sentences/second (CPU) |
| **MTEB Benchmark** | Top-10 among lightweight models |

It's small enough to run on CPU without a GPU, yet produces embeddings good enough for production-quality semantic search.

### Batch Embedding

```python
def get_embeddings(texts):
    return model.encode(texts).tolist()
```

All chunks are embedded in a **single batch call**. This is much faster than embedding one chunk at a time because the model can process multiple inputs in parallel.

---

## Step 3 — FAISS Vector Index

### What is FAISS?

**FAISS (Facebook AI Similarity Search)** is a library for efficient similarity search over large collections of dense vectors. It's like a hash map for vector spaces — you can search millions of vectors in milliseconds.

### How the Index is Built

```python
vectors = np.array(embeddings, dtype="float32")
faiss.normalize_L2(vectors)          # Normalize to unit length
_index = faiss.IndexFlatIP(384)      # Create Inner Product index
_index.add(vectors)                  # Add all vectors
```

**Step by step:**

1. Convert Python lists to NumPy float32 arrays (FAISS requires this format)
2. **L2-normalize** each vector so its length is exactly 1.0
3. Create a `IndexFlatIP` (flat inner product) index for 384-dimensional vectors
4. Add all vectors to the index — O(n) operation

### Why Normalize + Inner Product?

**Cosine similarity** between two vectors A and B is defined as:

```
cosine_similarity(A, B) = (A · B) / (|A| × |B|)
```

When vectors are L2-normalized (`|A| = |B| = 1`), this simplifies to:

```
cosine_similarity(A, B) = A · B  (dot product / inner product)
```

So **inner product on L2-normalized vectors = cosine similarity**. The `IndexFlatIP` computes the inner product efficiently.

### Persistence

```python
faiss.write_index(_index, "data/faiss/virat_kohli.index")
json.dump(chunks, open("data/faiss/virat_kohli.chunks.json", "w"))
```

After building, the index is saved to disk. On the next question about the same article, the index is loaded from disk in ~5ms instead of re-embedding in ~2 seconds.

---

## Step 4 — Retrieval (Similarity Search)

### How Search Works

```python
query_embedding = get_embedding("When was Virat Kohli born?")
vector = np.array([query_embedding], dtype="float32")
faiss.normalize_L2(vector)           # Must normalize query too!
scores, indices = _index.search(vector, k=6)
```

FAISS computes the inner product between the query vector and all stored chunk vectors and returns the indices of the `k=6` highest scoring chunks.

### Similarity Threshold

```python
SIMILARITY_THRESHOLD = 0.3

results = []
for score, i in zip(scores[0], indices[0]):
    if i != -1 and score >= SIMILARITY_THRESHOLD:
        results.append({"text": _documents[i], "score": float(score)})
```

Any chunk with a cosine similarity **below 0.30** is silently dropped. This threshold is important:

| Scenario | Without Threshold | With Threshold (0.30) |
|---|---|---|
| Question about birth date | All 6 slots filled, some irrelevant | Only 3-4 highly relevant chunks |
| Question about a topic not in article | 6 random weakly-related chunks sent to LLM → hallucination risk | 0 chunks → LLM says "not found" |

**Score interpretation:**
- `0.9-1.0` → Near-identical text
- `0.7-0.9` → Highly relevant
- `0.5-0.7` → Relevant
- `0.3-0.5` → Loosely relevant
- `< 0.3` → Off-topic

### Complexity

For `IndexFlatIP`, search is O(n × d) where:
- `n` = number of vectors (typically 30-200 for a Wikipedia article)
- `d` = dimension (384)

For a 100-chunk article: `100 × 384 = 38,400` multiply-accumulate operations. Modern CPUs perform billions per second — this takes **microseconds**.

---

## Step 5 — Generation (The LLM)

### The Prompt

```python
prompt = (
    "You are a Wikipedia-based QA assistant.\n"
    "Answer using ONLY the context below. Be concise.\n"
    'If the answer is not present, say: "I couldn\'t find that information."\n\n'
    f"CONTEXT:\n{context}\n\n"
    f"QUESTION: {question}"
)
```

The context is the joined text of the retrieved chunks:

```
CONTEXT:
Virat Kohli (born 5 November 1988) is an Indian international cricketer...

[NEXT CHUNK]
Kohli made his One Day International debut on 18 August 2008 against Sri Lanka...

[NEXT CHUNK]
In Test cricket, Kohli holds the record for the most centuries...

QUESTION: When was Virat Kohli born?
```

### The LLM's Job

The LLM reads the context and the question, then generates an answer. The key constraint: **"Answer using ONLY the context below."**

This prevents the LLM from supplementing with its training data (which may be outdated or wrong).

### Why `temperature=0.1`?

Temperature controls the randomness of the LLM's output:
- `temperature=0.0` → Fully deterministic, always picks the highest-probability token
- `temperature=1.0` → High creativity, varied output, more hallucination risk
- `temperature=0.1` → Near-deterministic, factual, consistent

For a Q&A system, we want the same question to always produce the same factual answer. Low temperature achieves this.

---

## How Hallucination is Reduced

RAG reduces hallucination through three mechanisms:

### 1. Context Grounding

The LLM is **explicitly instructed** to answer only from the provided context. If the answer isn't in the retrieved chunks, the LLM must say so — not fabricate an answer.

### 2. Relevance Filtering

The similarity threshold (`≥ 0.30`) ensures that only chunks **semantically related** to the question reach the LLM. Unrelated chunks that might trigger false associations are filtered out.

### 3. Source Transparency

Every answer is accompanied by the **source chunks** with their similarity scores. The user can read the exact Wikipedia text that was used and verify the answer. If the answer is wrong, the source will show it.

---

## Cache Hit vs Cache Miss

### Cache Miss (First time asking a question)

```
1. Check SQLite → not found                   [~1ms]
2. Check FAISS disk cache → exists            [~5ms]
   or build FAISS from scratch                [~2000ms for embedding]
3. Embed question                             [~50ms]
4. FAISS search                               [~1ms]
5. LLM call (Groq)                            [~1500ms]
6. Save to SQLite                             [~1ms]
Total: ~1.6-3.5 seconds
```

### Cache Hit (Question asked before)

```
1. Check SQLite → FOUND                       [~1ms]
2. Return cached result immediately
Total: <5ms
```

The cache key is `normalize(title + "::" + question)`, so:
- `"When was Virat Kohli born?"` and `"when was virat kohli born"` both hit the same cache entry
- `"Virat Kohli::When was he born?"` and `"Black Hole::When was he born?"` are different entries (different articles)

---

## Why FAISS?

FAISS is chosen over alternatives for this use case:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **FAISS** | In-process, zero latency, free, handles millions of vectors | No persistence built-in (we add it) | ✅ Best for this project |
| **Chroma** | Easy API, built-in persistence | External process dependency | Good alternative |
| **Pinecone** | Cloud-hosted, scales to billions | Paid, network latency, data leaves device | Overkill |
| **Linear search** | Zero setup | O(n) per query | Too slow at scale |
| **HNSW** | Faster approximate search | Approximate (not exact), more memory | Useful at >1M vectors |

For Wikipedia articles with 30-200 chunks, `IndexFlatIP` provides **exact** cosine similarity with microsecond search time. Approximate methods are unnecessary at this scale.

---

## Performance Analysis

### Embedding Time

```
Article: 50,000 characters (~10,000 words)
Chunks after splitting: ~45 chunks
Embedding 45 chunks: ~200ms (CPU, all-MiniLM-L6-v2)
```

After the first embedding, the FAISS index is cached to disk. Subsequent questions about the same article load in ~5ms.

### Search Time

```
FAISS search (k=6, n=45, d=384):
  Multiply-accumulate ops: 45 × 384 = 17,280
  At 10 GFLOPS CPU: 17,280 / 10,000,000,000 = 0.000002 seconds
  Actual measured: ~0.5ms (including Python overhead)
```

### LLM Time

```
Groq (LPU hardware, llama-3.1-8b-instant): 1-3 seconds
OpenRouter (free tier): 5-20 seconds
```

The biggest latency component is always the LLM call. FAISS and embeddings are negligible by comparison.

### End-to-End Time

| Scenario | Time |
|---|---|
| Answer cache hit | <5ms |
| FAISS index cached, Groq available | 1.5-3.5 seconds |
| Fresh embedding + Groq | 3-5 seconds |
| Fresh embedding + OpenRouter | 10-25 seconds |

---

## Visual Summary

```
                        THE RAG PIPELINE
                        ═══════════════

    Wikipedia Article (60,000 chars)
           │
           ▼
    ┌──────────────────────────────┐
    │  CHUNK                       │   500 tokens each
    │  "...born 5 Nov 1988..."     │   100 token overlap
    │  "...ODI debut 2008..."      │   → ~45 chunks
    │  "...Test records..."        │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │  EMBED                       │   all-MiniLM-L6-v2
    │  [0.23, -0.89, 0.10, ...]   │   384 dimensions
    │  [-0.45, 0.67, -0.12, ...]  │   per chunk
    │  [0.78, -0.34, 0.56, ...]   │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │  FAISS INDEX                 │   IndexFlatIP
    │  ║█████████████████║         │   Cosine similarity
    │  ║ 45 vectors ×384  ║         │   Persisted to disk
    └──────────────┬───────────────┘
                   │
      "When was Virat Kohli born?"
                   │
                   ▼
    ┌──────────────────────────────┐
    │  SEARCH                      │   Top-6 chunks
    │  score=0.87 → Chunk 1 ✓     │   score ≥ 0.30
    │  score=0.61 → Chunk 12 ✓    │   Filter noise
    │  score=0.23 → Chunk 33 ✗    │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │  LLM (Llama 3.1 8B)          │   temp=0.1
    │  "You are a QA assistant..." │   max_tokens=512
    │  CONTEXT: [retrieved chunks] │   Answer ONLY from
    │  QUESTION: When was he born? │   context
    └──────────────┬───────────────┘
                   │
                   ▼
    "Virat Kohli was born on 5 November 1988."
    + sources: [Chunk 1 (87%), Chunk 12 (61%)]
    + stats: total_chunks=45, retrieved=2, time=2.1s
```
