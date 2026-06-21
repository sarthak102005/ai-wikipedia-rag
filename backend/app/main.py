from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str


@app.get("/")
def home():
    return {
        "message": "AI Wikipedia RAG Backend is running!"
    }


@app.post("/search")
def search(request: SearchRequest):
    return {
        "received_query": request.query
    }