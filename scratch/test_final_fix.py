"""
End-to-end verification of the permanent table fix.
Tests both Test runs AND ODI runs to confirm column context is preserved.
"""
import json
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.rag import run_rag

def run_test(question):
    print(f"\n{'='*60}")
    print(f"Q: {question}")
    print('='*60)

    with open(r"c:\Users\SARTHAK MAKKAR\Documents\ai-wikipedia-rag\backend\data\articles\virat_kohli.json", "r", encoding="utf-8") as f:
        article_data = json.load(f)

    result = run_rag(
        article=article_data.get("full_content", ""),
        question=question,
        title=article_data.get("title", ""),
        images=article_data.get("images", []),
        tables=article_data.get("tables", []),
    )

    print(f"Answer: {result['answer']}")
    print(f"Chunks: {result['total_chunks']} total, {result['retrieved_chunks']} retrieved")
    print("\nTop retrieved source:")
    if result["sources"]:
        src = result["sources"][0]
        print(f"  [{src['method']}] score={src['score']:.4f}")
        print(f"  {src['text'][:250]}")

if __name__ == "__main__":
    questions = [
        "What is the total Test runs scored by Virat Kohli?",
        "What is the total ODI runs scored by Virat Kohli?",
        "What is Virat Kohli's T20I batting average?",
        "How many Test centuries has Virat Kohli scored?",
        "What is Virat Kohli's height?",
    ]
    for q in questions:
        run_test(q)
