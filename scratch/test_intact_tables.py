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

def test_intact_tables(question):
    article_path = r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\articles\virat_kohli.json"
    with open(article_path, "r", encoding="utf-8") as f:
        article_data = json.load(f)
        
    title = article_data.get("title", "Virat Kohli")
    
    # 1. Get raw content *without* the tables appended
    full_content = article_data.get("full_content", "")
    # Strip the appended tables section if it's already there
    if "\n\n== Tables and Statistics ==" in full_content:
        full_content = full_content.split("\n\n== Tables and Statistics ==")[0]
        
    # 2. Split prose content into chunks
    prose_chunks = _split_text(full_content)
    prepended_chunks = [f"Article: {title}\n\n{c}" for c in prose_chunks]
    
    # 3. Format and add each table as an intact chunk
    tables = article_data.get("tables", [])
    print(f"Adding {len(tables)} tables as intact chunks...")
    for idx, t in enumerate(tables):
        caption = t.get("caption", "").strip() or f"Table {idx+1}"
        headers = t.get("headers", [])
        rows = t.get("rows", [])
        
        md_lines = [f"Article: {title}", f"Table: {caption}\n"]
        if headers:
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            md_lines.append("| " + " | ".join(row) + " |")
            
        table_md = "\n".join(md_lines)
        prepended_chunks.append(table_md)
        
    print(f"Total chunks (prose + intact tables): {len(prepended_chunks)}")
    
    # 4. Embed and index
    embeddings = get_embeddings(prepended_chunks)
    vectors = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vectors)
    
    index = faiss.IndexFlatIP(384)
    index.add(vectors)
    
    # 5. Search
    q_emb = np.array([get_embedding(question)], dtype="float32")
    faiss.normalize_L2(q_emb)
    
    k = 6
    scores, indices = index.search(q_emb, k)
    
    retrieved_chunks = []
    print("\n--- Retrieved Chunks ---")
    for score, idx in zip(scores[0], indices[0]):
        text = prepended_chunks[idx]
        retrieved_chunks.append(text)
        print(f"- score: {score:.4f}\n  {repr(text[:300])}...\n")
        
    # 6. Ask LLM
    context = "\n\n".join(retrieved_chunks)
    answer = ask_llm(context, question)
    
    print("\n--- Generated Answer ---")
    print(answer)

if __name__ == "__main__":
    q = "What is the total Test runs scored by Virat Kohli?"
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    print(f"Question: {q}")
    test_intact_tables(q)
