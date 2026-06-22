import faiss
import numpy as np

dimension = 384
index = faiss.IndexFlatL2(dimension)

documents = []


def build_index(chunks, embeddings):
    global documents

    documents = chunks

    vectors = np.array(embeddings).astype("float32")

    index.reset()
    index.add(vectors)


def search(query_embedding, k=4):

    vector = np.array([query_embedding]).astype("float32")

    _, indices = index.search(vector, k)

    return [
        documents[i]
        for i in indices[0]
        if i != -1
    ]