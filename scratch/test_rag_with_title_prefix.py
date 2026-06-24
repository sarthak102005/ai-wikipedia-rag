import json
import sys
import os
import numpy as np

# Add backend to sys.path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.embeddings import get_embedding, get_embeddings
from app.llm import ask_llm
from app.rag import _split_text
import faiss

def test_rag_with_prefix():
    article_path = r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\articles\virat_kohli.json"
    with open(article_path, "r", encoding="utf-8") as f:
        article_data = json.load(f)
        
    full_content = article_data.get("full_content", "")
    title = "Virat Kohli"
    
    # Split text and prepend title
    raw_chunks = _split_text(full_content)
    prepended_chunks = [f"Article: {title}\n\n{c}" for c in raw_chunks]
    
    print(f"Total chunks: {len(prepended_chunks)}")
    
    # Get embeddings and index
    embeddings = get_embeddings(prepended_chunks)
    vectors = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vectors)
    
    index = faiss.IndexFlatIP(384)
    index.add(vectors)
    
    # Query
    question = "What is the total ODI runs scored by Virat Kohli?"
    q_emb = np.array([get_embedding(question)], dtype="float32")
    faiss.normalize_L2(q_emb)
    
    # Search
    k = 6
    scores, indices = index.search(q_emb, k)
    
    retrieved_chunks = []
    print("\n--- Retrieved Chunks ---")
    for score, idx in zip(scores[0], indices[0]):
        text = prepended_chunks[idx]
        retrieved_chunks.append(text)
        print(f"- score: {score:.4f}\n  {repr(text[:300])}...\n")
        
    # Generate answer
    context = "\n\n".join(retrieved_chunks)
    answer = ask_llm(context, question)
    
    print("\n--- Generated Answer ---")
    print(answer)

if __name__ == "__main__":
    test_rag_with_prefix()
