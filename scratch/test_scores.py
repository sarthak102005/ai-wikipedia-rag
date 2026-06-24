import json
import sys
import os
import numpy as np

# Add backend to sys.path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.embeddings import get_embedding, get_embeddings
import faiss

def test_scores():
    # Load chunks
    chunks_path = r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\faiss\Virat Kohli.chunks.json"
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
        
    # Load index
    index_path = r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\faiss\Virat Kohli.index"
    index = faiss.read_index(index_path)
    
    # Query embedding
    query = "What is the total ODI runs scored by Virat Kohli?"
    q_emb = np.array([get_embedding(query)], dtype="float32")
    faiss.normalize_L2(q_emb)
    
    # Get all scores
    # Reconstruct vectors or run search for all elements
    scores, indices = index.search(q_emb, len(chunks))
    
    print("Top 10 chunks by similarity score:")
    for rank, (score, idx) in enumerate(zip(scores[0][:15], indices[0][:15])):
        chunk_text = chunks[idx]
        has_val = "14,797" in chunk_text or "14797" in chunk_text
        print(f"Rank {rank+1} (Index {idx}): score = {score:.4f} | Has 14,797: {has_val}")
        print(f"  {repr(chunk_text[:150])}...")
        
    print("\n--- Scores of chunks containing 14,797 ---")
    for idx, chunk_text in enumerate(chunks):
        if "14,797" in chunk_text:
            # Find rank of this index
            rank_idx = np.where(indices[0] == idx)[0][0]
            score_idx = scores[0][rank_idx]
            print(f"Index {idx} (Rank {rank_idx+1}): score = {score_idx:.4f}")
            print(f"  Text: {repr(chunk_text)}")

if __name__ == "__main__":
    test_scores()
