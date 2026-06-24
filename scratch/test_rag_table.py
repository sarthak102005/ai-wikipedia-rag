import json
import requests

def test_rag_table():
    with open(r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\articles\virat_kohli.json", "r", encoding="utf-8") as f:
        article_data = json.load(f)
        
    full_content = article_data.get("full_content", "")
    print("Full content length:", len(full_content))
    
    url = "http://127.0.0.1:8001/ask"
    payload = {
        "article": full_content,
        "question": "What is the total ODI runs scored by Virat Kohli?",
        "title": "Virat Kohli",
        "images": []
    }
    
    resp = requests.post(url, json=payload)
    print("Status code:", resp.status_code)
    data = resp.json()
    print("\nAnswer:", data.get("answer"))
    print("\nTotal Chunks:", data.get("total_chunks"))
    print("Retrieved Chunks:", data.get("retrieved_chunks"))
    print("\nSources:")
    for src in data.get("sources", []):
        print(f"- [{src.get('method')}] score: {src.get('score'):.4f}\n  {src.get('text')[:200]}...")

test_rag_table()
