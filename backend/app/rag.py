from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import get_embedding, get_embeddings
from app.vector_store import build_index, search
from app.llm import ask_llm


def split_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )
    return splitter.split_text(text)


def run_rag(article, question):

    chunks = split_text(article)

    embeddings = get_embeddings(chunks)
    build_index(chunks, embeddings)

    query_embedding = get_embedding(question)

    retrieved = search(query_embedding)

    context = "\n\n".join(retrieved)

    return ask_llm(context, question)