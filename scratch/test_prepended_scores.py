import json
import sys
import os
import numpy as np

# Add backend to sys.path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.embeddings import get_embedding, get_embeddings
import faiss

def test_prepended_scores():
    # Load chunks
    chunks_path = r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\faiss\Virat Kohli.chunks.json"
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
        
    title = "Virat Kohli"
    prepended_chunks = [f"Article: {title}\n\n{c}" for c in chunks]
    
    # Get embeddings for prepended chunks
    print("Re-embedding all chunks with prepended title...")
    embeddings = get_embeddings(prepended_chunks)
    
    vectors = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vectors)
    
    # Build temporary FAISS index
    index = faiss.IndexFlatIP(384)
    index.add(vectors)
    
    # Query embedding
    query = "What is the total ODI runs scored by Virat Kohli?"
    q_emb = np.array([get_embedding(query)], dtype="float32")
    faiss.normalize_L2(q_emb)
    
    # Search
    scores, indices = index.search(q_emb, len(chunks))
    
    print("\nTop 15 chunks by similarity score (with prepended title):")
    for rank, (score, idx) in enumerate(zip(scores[0][:15], indices[0][:15])):
        chunk_text = prepended_chunks[idx]
        has_val = "14,797" in chunk_text
        print(f"Rank {rank+1} (Index {idx}): score = {score:.4f} | Has 14,797: {has_val}")
        print(f"  {repr(chunk_text[:150])}...")
        
    print("\n--- Scores of chunks containing 14,797 (with prepended title) ---")
    for idx, chunk_text in enumerate(prepended_chunks):
        if "14,797" in chunk_text:
            rank_idx = np.where(indices[0] == idx)[0][0]
            score_idx = scores[0][rank_idx]
            print(f"Index {idx} (Rank {rank_idx+1}): score = {score_idx:.4f}")
            print(f"  Text: {repr(chunk_text)}")

if __name__ == "__main__":
    test_prepended_scores()
