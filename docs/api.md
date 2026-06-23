# 📡 API Documentation

This document provides complete documentation for all API endpoints exposed by the FastAPI backend.

**Base URL:** `http://127.0.0.1:8001`  
**Auto-generated interactive docs:** `http://127.0.0.1:8001/docs` (Swagger UI)  
**OpenAPI schema:** `http://127.0.0.1:8001/openapi.json`

---

## Table of Contents

- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [GET /](#get-)
  - [POST /search](#post-search)
  - [POST /ask](#post-ask)
- [Response Codes](#response-codes)
- [Error Responses](#error-responses)
- [Rate Limiting](#rate-limiting)
- [CORS Configuration](#cors-configuration)
- [Example Integration (JavaScript)](#example-integration-javascript)
- [Example Integration (Python)](#example-integration-python)
- [Example Integration (cURL)](#example-integration-curl)

---

## Authentication

The backend does **not** require authentication. It is designed for local development use.

API keys for Groq and OpenRouter are configured server-side in `backend/.env` and are never exposed to the client.

---

## Endpoints

### `GET /`

**Health check.** Verifies that the backend server is running.

#### Request

```
GET http://127.0.0.1:8001/
```

No request body required.

#### Response

**Status:** `200 OK`

```json
{
  "message": "AI Wikipedia RAG Backend is running!",
  "version": "2.0.0"
}
```

#### Use Case

Call this endpoint before making other requests to confirm the backend is up. The frontend shows `"Failed to connect to backend. Is the server running?"` when this is unreachable.

---

### `POST /search`

**Search Wikipedia.** Resolves the query through OpenSearch (with typo correction), then fetches and caches the article summary, full text, image, and URL.

#### Request

**Content-Type:** `application/json`

**Body:**

```json
{
  "query": "string (required)"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | ✅ | The search term. Can be a topic name, a person's name (even with typos), a concept, etc. |

**Example Request:**

```json
{
  "query": "virat kholi"
}
```

#### Response

**Status:** `200 OK`

**Success Response:**

```json
{
  "title": "Virat Kohli",
  "summary": "Virat Kohli (born 5 November 1988) is an Indian international cricketer who currently captains the Royal Challengers Bengaluru...",
  "full_content": "Virat Kohli (born 5 November 1988) is an Indian international cricketer...\n\nEarly life\nKohli was born in Delhi...\n\n[Full article text - typically 10,000-80,000 characters]",
  "url": "https://en.wikipedia.org/wiki/Virat_Kohli",
  "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Virat_Kohli.jpg/320px-Virat_Kohli.jpg",
  "corrected_query": "Virat Kohli",
  "original_query": "virat kholi"
}
```

**Response Fields:**

| Field | Type | Always Present | Description |
|---|---|---|---|
| `title` | `string` | ✅ | Canonical Wikipedia article title |
| `summary` | `string` | ✅ | First paragraph of the article (Wikipedia extract) |
| `full_content` | `string` | ✅ | Complete plain-text article body |
| `url` | `string` | ✅ | Desktop Wikipedia URL for the article |
| `image` | `string \| null` | ✅ | URL to article thumbnail image; `null` if no image |
| `corrected_query` | `string` | ❌ | The corrected title, present only if the query was auto-corrected |
| `original_query` | `string` | ❌ | The original user query, present only if auto-corrected |
| `error` | `string` | ❌ | Error message, present only on failure; other fields absent |

**Error Responses:**

```json
{ "error": "No Wikipedia article found for \"xyzzy123\"." }
```

```json
{ "error": "Wikipedia is temporarily unavailable. Please try again later." }
```

```json
{ "error": "Wikipedia request timed out. Please try again." }
```

```json
{ "error": "Wikipedia request failed. Please check your internet connection." }
```

#### Notes

- If the query is slightly misspelled (e.g., `"einsteinn"`, `"virat kholi"`), OpenSearch automatically resolves to the best-matching title
- On repeat requests for the same article, responses come from cache (disk or memory) — network requests to Wikipedia are skipped entirely
- The `full_content` field is the text sent to the RAG pipeline when the user asks a question

---

### `POST /ask`

**Ask an AI question using the RAG pipeline.** Splits the provided article text into chunks, embeds them, performs similarity search, and calls the LLM with retrieved context.

#### Request

**Content-Type:** `application/json`

**Body:**

```json
{
  "article": "string (required)",
  "question": "string (required)",
  "title": "string (optional, default: '')"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `article` | `string` | ✅ | The full article text to search over. Use `full_content` from `/search`. Falls back to `summary` if unavailable. |
| `question` | `string` | ✅ | The natural language question to answer. |
| `title` | `string` | ❌ | The article title used as the FAISS index key. If provided, enables index caching — the same article won't be re-embedded on subsequent questions. |

**Example Request:**

```json
{
  "article": "Virat Kohli (born 5 November 1988) is an Indian international cricketer...",
  "question": "When was Virat Kohli born?",
  "title": "Virat Kohli"
}
```

#### Response

**Status:** `200 OK`

**Success Response (Cache MISS — first time asking):**

```json
{
  "answer": "Virat Kohli was born on 5 November 1988.",
  "sources": [
    {
      "text": "Virat Kohli (born 5 November 1988) is an Indian international cricketer who currently captains the Royal Challengers Bengaluru in the Indian Premier League and represents Delhi in domestic cricket.",
      "score": 0.8734219670295715
    },
    {
      "text": "Kohli was born in Delhi on 5 November 1988 to a Punjabi family. His father, Prem Kohli, worked as a criminal lawyer and his mother, Saroj Kohli, is a housewife.",
      "score": 0.6892341375350952
    }
  ],
  "total_chunks": 42,
  "retrieved_chunks": 2,
  "cache_hit": false,
  "time": "2.34 s"
}
```

**Success Response (Cache HIT — question asked before):**

```json
{
  "answer": "Virat Kohli was born on 5 November 1988.",
  "sources": [
    {
      "text": "Virat Kohli (born 5 November 1988) is an Indian international cricketer...",
      "score": 0.8734219670295715
    }
  ],
  "total_chunks": 42,
  "retrieved_chunks": 2,
  "cache_hit": true,
  "time": "0.001 s"
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `answer` | `string` | The AI-generated answer, grounded in the retrieved chunks |
| `sources` | `array` | List of retrieved text chunks used to generate the answer |
| `sources[].text` | `string` | The actual Wikipedia text chunk |
| `sources[].score` | `float` | Cosine similarity score [0.0, 1.0] between chunk and question |
| `total_chunks` | `integer` | Total number of chunks the article was split into |
| `retrieved_chunks` | `integer` | Number of chunks actually used (passed to LLM) |
| `cache_hit` | `boolean` | `true` if the answer was served from SQLite cache |
| `time` | `string` | Total response time including all pipeline steps, e.g. `"2.34 s"` |

**Graceful Error Responses (still HTTP 200):**

When the pipeline encounters a recoverable issue, it returns a valid JSON response with an error message in the `answer` field rather than crashing:

```json
{
  "answer": "No article content was provided.",
  "sources": [],
  "total_chunks": 0,
  "retrieved_chunks": 0,
  "cache_hit": false,
  "time": "0.001 s"
}
```

```json
{
  "answer": "The article content is too short to process.",
  "sources": [],
  "total_chunks": 0,
  "retrieved_chunks": 0,
  "cache_hit": false,
  "time": "0.002 s"
}
```

```json
{
  "answer": "I couldn't find that information in the article.",
  "sources": [],
  "total_chunks": 42,
  "retrieved_chunks": 0,
  "cache_hit": false,
  "time": "0.15 s"
}
```

```json
{
  "answer": "The AI service timed out. Please try again in a moment.",
  "sources": [],
  "total_chunks": 42,
  "retrieved_chunks": 4,
  "cache_hit": false,
  "time": "20.05 s"
}
```

#### Notes

- The `title` field is critical for FAISS index caching. Always pass `result.title` from the `/search` response
- The LLM is instructed to only answer from the provided context. If the answer is not in the article, it will say so rather than hallucinating
- Both `/search` and `/ask` responses are cached persistently in SQLite and survive server restarts

---

## Response Codes

| Code | Description |
|---|---|
| `200 OK` | Request processed successfully (includes business-logic errors in response body) |
| `422 Unprocessable Entity` | Request body failed Pydantic validation (e.g., missing required field, wrong type) |
| `500 Internal Server Error` | Unexpected server error (rare; most errors are handled gracefully) |

### 422 Example

If you call `/search` without the `query` field:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "query"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

---

## Error Responses

The API follows a consistent error pattern: **HTTP errors** (4xx, 5xx) for protocol-level issues, and **JSON errors** in the response body for application-level issues.

| Error Type | HTTP Code | `error` field in body |
|---|---|---|
| Missing required field | 422 | N/A (Pydantic returns `detail`) |
| Article not found on Wikipedia | 200 | `"No Wikipedia article found for '...'."` |
| Wikipedia down | 200 | `"Wikipedia is temporarily unavailable."` |
| Wikipedia timeout | 200 | `"Wikipedia request timed out."` |
| No internet | 200 | `"Wikipedia request failed. Check your internet."` |
| Article too short to process | 200 | `"The article content is too short to process."` |
| Answer not in article | 200 | `"I couldn't find that information in the article."` |
| LLM timeout | 200 | `"The AI service timed out. Please try again."` |
| LLM connection error | 200 | `"Could not connect to the AI service."` |

---

## Rate Limiting

The backend itself has **no rate limiting**. However, external services do:

| Service | Limit |
|---|---|
| Wikipedia API | Very generous; effectively unlimited for normal use |
| Groq (free tier) | 6,000 tokens/minute |
| OpenRouter (free tier) | Varies by model; typically 10-20 requests/hour |

When Groq rate-limiting occurs (HTTP 429), the backend automatically falls back to OpenRouter with no user-visible error.

---

## CORS Configuration

The backend only allows requests from `http://localhost:5173` (Vite dev server):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production deployment, replace `"http://localhost:5173"` with your frontend's production URL.

---

## Example Integration (JavaScript)

```javascript
// Search Wikipedia
const searchResult = await fetch("http://127.0.0.1:8001/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: "Albert Einstein" }),
}).then(r => r.json());

console.log(searchResult.title);    // "Albert Einstein"
console.log(searchResult.image);    // "https://upload.wikimedia.org/..."

// Ask a question using RAG
const ragResult = await fetch("http://127.0.0.1:8001/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
        article: searchResult.full_content,
        question: "What is Einstein famous for?",
        title: searchResult.title,
    }),
}).then(r => r.json());

console.log(ragResult.answer);          // "Einstein is famous for..."
console.log(ragResult.cache_hit);       // false (first time)
console.log(ragResult.total_chunks);    // 38
console.log(ragResult.sources[0].score); // 0.91
```

---

## Example Integration (Python)

```python
import requests

BASE = "http://127.0.0.1:8001"

# Search Wikipedia
search_res = requests.post(f"{BASE}/search", json={"query": "Black hole"}).json()
print(f"Title: {search_res['title']}")

# Ask a question
rag_res = requests.post(f"{BASE}/ask", json={
    "article": search_res["full_content"],
    "question": "What happens to time near a black hole?",
    "title": search_res["title"],
}).json()

print(f"Answer: {rag_res['answer']}")
print(f"Sources: {len(rag_res['sources'])} chunks used")
print(f"Time: {rag_res['time']}")
print(f"Cache hit: {rag_res['cache_hit']}")
```

---

## Example Integration (cURL)

```bash
# Health check
curl http://127.0.0.1:8001/

# Search
curl -X POST http://127.0.0.1:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "photosynthesis"}'

# Ask AI
curl -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{
    "article": "Photosynthesis is the process by which plants...",
    "question": "What do plants need for photosynthesis?",
    "title": "Photosynthesis"
  }'
```
