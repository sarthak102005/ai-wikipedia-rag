import os
os.environ["HF_HUB_OFFLINE"] = "1"

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embedding(text: str):
    try:
        emb = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
    except TypeError:
        emb = model.encode(text)
    return emb.astype("float32").tolist()


def get_embeddings(texts):
    try:
        emb = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )
    except TypeError:
        emb = model.encode(texts)
    return emb.astype("float32").tolist()
