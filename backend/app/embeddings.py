import os
from sentence_transformers import SentenceTransformer

# Set offline mode before loading model
os.environ["HF_HUB_OFFLINE"] = "1"

# Load model with local_files_only to work in offline/restricted network environments
try:
    model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    print(f"Warning: Could not load embedding model: {e}")
    model = None


def get_embedding(text: str):
    if model is None:
        raise RuntimeError("Embedding model failed to load. Check internet connection or model cache.")
    return model.encode(text).tolist()


def get_embeddings(texts):
    if model is None:
        raise RuntimeError("Embedding model failed to load. Check internet connection or model cache.")
    return model.encode(texts).tolist()