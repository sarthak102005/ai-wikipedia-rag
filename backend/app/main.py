import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any

from app.wikipedia_api import search_wikipedia
from app.rag import run_rag

app = FastAPI(title="AI Wikipedia RAG", version="3.0.0")

# CORS configuration: support local development and production Vercel frontend
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:5174",   # Vite fallback port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

# Add production frontend URL from environment if available
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
    article:  str               # Full article text (preferred) or summary
    question: str
    title:    str = ""          # Article title — used as FAISS index key
    images:   list[Any] = []   # All page images — for semantic matching
    tables:   list[Any] = []   # Parsed Wikipedia tables — for structured indexing


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
    return run_rag(request.article, request.question, request.title, request.images, request.tables)


# Serve static files from the built frontend directory
frontend_dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist_dir):
    print(f"[main] Mounting static files from: {frontend_dist_dir}")
    app.mount("/", StaticFiles(directory=frontend_dist_dir, html=True), name="static")

    # Catch-all route to serve index.html for SPA routing
    @app.get("/{catchall:path}")
    async def read_index(catchall: str):
        index_path = os.path.join(frontend_dist_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
else:
    print(f"[main] Warning: static files directory not found at: {frontend_dist_dir}")