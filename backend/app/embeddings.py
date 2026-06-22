from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embedding(text: str):
    return model.encode(text).tolist()


def get_embeddings(texts):
    return model.encode(texts).tolist()