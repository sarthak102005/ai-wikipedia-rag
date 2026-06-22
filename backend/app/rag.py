from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import get_embedding, get_embeddings
from app.vector_store import build_index, search
from app.llm import ask_llm
from app.cache import cache


def split_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )
    return splitter.split_text(text)


def run_rag(article, question):

    key = question.strip().lower()

    if key in cache:
        return cache[key]

    if not article or article.strip() == "":
        result = {
            "answer": "No article provided.",
            "sources": []
        }
        cache[key] = result
        return result

    chunks = split_text(article)

    embeddings = get_embeddings(chunks)

    build_index(chunks, embeddings)

    query_embedding = get_embedding(question)

    retrieved = search(query_embedding)

    if not retrieved:
        result = {
            "answer": "I couldn't find that information in the article.",
            "sources": []
        }
        cache[key] = result
        return result

    context = "\n\n".join(retrieved)

    answer = ask_llm(context, question)

    result = {
        "answer": answer,
        "sources": retrieved
    }

    cache[key] = result

    return result