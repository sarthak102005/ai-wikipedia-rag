import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.cache import cache
from app.utils import normalize_cache_key
from app.wikipedia_api import search_wikipedia
from app.embeddings import get_embedding, get_embeddings
from app.vector_store import build_index, search, index_exists, load_index
from app.rag import run_rag

print("=== 1. Imports ===          All imports OK")

# Test cache
print("=== 2. Cache (SQLite) ===")
try:
    cache["test_key"] = "test_value"
    assert cache["test_key"] == "test_value"
    assert "test_key" in cache
    print("   Read/write OK")
except Exception as e:
    print(f"   Cache error: {e}")
    sys.exit(1)

# Test normalize cache key
print("=== 3. normalize_cache_key ===")
try:
    normalized = normalize_cache_key("  Virat   Kohli  ")
    assert normalized == "virat kohli"
    print("   normalize_cache_key OK")
except Exception as e:
    print(f"   normalize_cache_key failed: {e}")
    sys.exit(1)

# Test Wikipedia API
print("=== 4. Wikipedia search ===")
try:
    res = search_wikipedia("virat kholi")
    print(f"   'virat kholi' -> '{res.get('title')}' (corrected: {res.get('corrected_query')})")
    assert "Virat Kohli" in res.get("title", "")
    assert len(res.get("full_content", "")) > 1000
    print(f"   full_content: {len(res.get('full_content'))} chars  [OK]")
except Exception as e:
    print(f"   Wikipedia search failed: {e}")
    sys.exit(1)

# Test RAG
print("=== 5. RAG ===")
try:
    title = res.get("title")
    article = res.get("full_content")
    question = "Who is Virat Kohli?"
    rag_res = run_rag(article, question, title)
    ans = rag_res.get("answer", "")
    enc = sys.stdout.encoding or "ascii"
    print("   RAG answer:", ans.encode(enc, errors="replace").decode(enc))
    print("   Sources count:", len(rag_res.get("sources", [])))
    assert len(rag_res.get("sources", [])) > 0
    print("   RAG run OK")
except Exception as e:
    print(f"   RAG run failed: {e}")
    sys.exit(1)

print("=== ALL TESTS PASSED ===")
