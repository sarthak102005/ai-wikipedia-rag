import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any

from app.wikipedia_api import search_wikipedia
from app.rag import run_rag
from app.chat_store import get_messages, add_message, clear_messages

app = FastAPI(title="AI Wikipedia RAG", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# Request models
# ─────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str


class AskRequest(BaseModel):
    article:  str               # Full article text (preferred) or summary
    question: str
    title:    str = ""          # Article title — used as FAISS index key
    images:   list[Any] = []   # All page images — for semantic matching
    tables:   list[Any] = []   # Parsed Wikipedia tables — for structured indexing
    conversation_history: list[dict] = []  # optional conversation history from client


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "message": "AI Wikipedia RAG Backend is running!", "version": "4.0.0"}


@app.post("/search")
def search(request: SearchRequest):
    return search_wikipedia(request.query)


@app.post("/ask")
def ask(request: AskRequest):
    result = run_rag(request.article, request.question, request.title, request.images, request.tables, request.conversation_history)
    # persist a lightweight chat entry (no heavy sources) for conversation history
    try:
        entry = {
            "question": request.question,
            "answer": result.get("answer", ""),
            "confidence": result.get("confidence_score", 0.0),
            "time": result.get("time", ""),
        }
        add_message(entry)
    except Exception:
        pass
    return result


@app.get("/chat")
def chat_get():
    return {"messages": get_messages()}


class ChatPostRequest(BaseModel):
    question: str
    answer: str
    confidence: float = 0.0
    time: str = ""


@app.post("/chat")
def chat_post(request: ChatPostRequest):
    entry = {"question": request.question, "answer": request.answer, "confidence": request.confidence, "time": request.time}
    messages = add_message(entry)
    return {"messages": messages}


@app.delete("/chat")
def chat_clear():
    clear_messages()
    return {"messages": []}


# Serve static files from the built frontend directory
frontend_dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist_dir):
    print(f"[main] Mounting static files from: {frontend_dist_dir}")
    app.mount("/", StaticFiles(directory=frontend_dist_dir, html=True), name="static")
else:
    print(f"[main] Warning: static files directory not found at: {frontend_dist_dir}")

    @app.get("/")
    def root():
        return {"message": "Frontend not built. API is running."}