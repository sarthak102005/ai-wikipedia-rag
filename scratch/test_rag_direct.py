import json
import sys
import os

# Add backend to sys.path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.rag import run_rag

def test():
    article_path = r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\articles\virat_kohli.json"
    with open(article_path, "r", encoding="utf-8") as f:
        article_data = json.load(f)
        
    full_content = article_data.get("full_content", "")
    print("Full content length:", len(full_content))
    
    # Run the query
    result = run_rag(
        article=full_content,
        question="What is the total ODI runs scored by Virat Kohli?",
        title="Virat Kohli",
        images=article_data.get("images", [])
    )
    
    print("\nAnswer:\n", result.get("answer"))
    print("\nTotal chunks:", result.get("total_chunks"))
    print("Retrieved chunks:", result.get("retrieved_chunks"))
    print("\nSources:")
    for src in result.get("sources", []):
        print(f"- [{src.get('method')}] score: {src.get('score'):.4f}\n  {src.get('text')}\n")

if __name__ == "__main__":
    test()
