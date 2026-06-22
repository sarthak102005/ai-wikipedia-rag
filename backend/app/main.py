from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.wikipedia_api import search_wikipedia
from app.rag import run_rag

app = FastAPI(title="AI Wikipedia RAG", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# Request models
# ─────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str


class AskRequest(BaseModel):
    article: str       # Full article text (preferred) or summary
    question: str
    title: str = ""    # Article title — used as FAISS index key on disk


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@app.get("/")
def home():
    return {"message": "AI Wikipedia RAG Backend is running!", "version": "2.0.0"}


@app.post("/search")
def search(request: SearchRequest):
    return search_wikipedia(request.query)


@app.post("/ask")
def ask(request: AskRequest):
    return run_rag(request.article, request.question, request.title)