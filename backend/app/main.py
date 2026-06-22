from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.wikipedia_api import search_wikipedia
from app.rag import run_rag

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- REQUEST MODELS ----------------
class SearchRequest(BaseModel):
    query: str


class AskRequest(BaseModel):
    article: str
    question: str


# ---------------- ROOT ----------------
@app.get("/")
def home():
    return {"message": "AI Wikipedia RAG Backend is running!"}


# ---------------- WIKIPEDIA SEARCH ----------------
@app.post("/search")
def search(request: SearchRequest):
    return search_wikipedia(request.query)


# ---------------- RAG ASK ----------------
@app.post("/ask")
def ask(request: AskRequest):

    return run_rag(
        request.article,
        request.question
    )