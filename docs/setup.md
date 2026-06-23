# 🚀 Setup Guide

This guide walks you through setting up the AI Wikipedia RAG project from scratch on your local machine. It covers prerequisites, installation, configuration, and running both the backend and frontend.

---

## Table of Contents

- [System Requirements](#system-requirements)
- [Step 1 — Clone the Repository](#step-1--clone-the-repository)
- [Step 2 — Backend Setup](#step-2--backend-setup)
- [Step 3 — Configure API Keys](#step-3--configure-api-keys)
- [Step 4 — Run the Backend](#step-4--run-the-backend)
- [Step 5 — Frontend Setup](#step-5--frontend-setup)
- [Step 6 — Run the Frontend](#step-6--run-the-frontend)
- [Step 7 — Verify Installation](#step-7--verify-installation)
- [Environment Variables Reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)
- [Updating Dependencies](#updating-dependencies)

---

## System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| **Operating System** | Windows 10, macOS 12, Ubuntu 20.04 | Windows 11 / macOS 14 / Ubuntu 22.04 |
| **Python** | 3.10 | 3.11 or 3.12 |
| **Node.js** | 18.x | 20.x (LTS) |
| **RAM** | 4 GB | 8 GB (embedding model needs ~1.5 GB) |
| **Disk Space** | 3 GB | 5 GB (model files + article cache) |
| **Internet** | Required for Wikipedia + LLM API calls | — |

> **GPU is not required.** The `all-MiniLM-L6-v2` embedding model runs efficiently on CPU.

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/yourusername/ai-wikipedia-rag.git
cd ai-wikipedia-rag
```

Your directory structure should look like:

```
ai-wikipedia-rag/
├── README.md
├── requirements.txt
├── backend/
├── frontend/
└── docs/
```

---

## Step 2 — Backend Setup

### Create a Virtual Environment

It is strongly recommended to use a Python virtual environment to isolate dependencies.

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If you get an execution policy error on Windows:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**macOS / Linux:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the beginning of your terminal prompt.

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- FastAPI + Uvicorn (web server)
- sentence-transformers (embedding model)
- faiss-cpu (vector database)
- LangChain text splitters (chunking)
- openai SDK (Groq + OpenRouter client)
- requests (Wikipedia API calls)
- python-dotenv (env var management)
- PyTorch (required by sentence-transformers)

> ⏱️ **First install takes 5-10 minutes** — PyTorch and sentence-transformers are large packages (~2.5 GB total)

---

## Step 3 — Configure API Keys

### Get API Keys

**Groq (Recommended — Primary LLM):**
1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign up for a free account
3. Navigate to API Keys → Create API Key
4. Copy your key (starts with `gsk_...`)
5. Free tier: 6,000 tokens/minute, no credit card required

**OpenRouter (Fallback LLM):**
1. Go to [https://openrouter.ai](https://openrouter.ai)
2. Sign up and navigate to Keys
3. Create a new API key
4. Copy your key (starts with `sk-or-...`)

### Configure the `.env` File

Edit `backend/.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
GROQ_API_KEY=gsk_your-groq-key-here
```

> ⚠️ **Never commit this file to Git.** It's already in `.gitignore`.

**Minimum viable setup:** You need at least one of the two keys. Groq is recommended for speed.

---

## Step 4 — Run the Backend

Navigate to the **project root** (not the `backend/` folder):

```bash
# From ai-wikipedia-rag/ (project root)
uvicorn backend.app.main:app --reload --port 8001
```

**Expected output:**
```
INFO:     Will watch for changes in these directories: ['C:\\...\\ai-wikipedia-rag']
INFO:     Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Alternative: Run from the backend/ folder

```bash
cd backend
uvicorn app.main:app --reload --port 8001
```

### What Happens on First Startup?

1. FastAPI app initializes
2. SQLite database `backend/data/cache.db` is created (if it doesn't exist)
3. Article store directory `backend/data/articles/` is created
4. FAISS index directory `backend/data/faiss/` is created
5. The `all-MiniLM-L6-v2` embedding model is **not** loaded yet — it loads on the first `/ask` request

> ℹ️ The embedding model downloads from HuggingFace (~22 MB) on the **very first** `/ask` request. Subsequent startups load it from local cache.

---

## Step 5 — Frontend Setup

Open a **new terminal** (keep the backend running in the first one):

```bash
cd frontend
npm install
```

This installs React, Vite, and other JavaScript dependencies into `frontend/node_modules/`.

> ⏱️ **First install takes 1-2 minutes** depending on internet speed

---

## Step 6 — Run the Frontend

```bash
# From frontend/ directory
npm run dev
```

**Expected output:**
```
  VITE v8.x.x  ready in 234 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

Open [**http://localhost:5173**](http://localhost:5173) in your browser.

---

## Step 7 — Verify Installation

1. **Backend health check:** Open `http://127.0.0.1:8001` in your browser
   - You should see: `{"message": "AI Wikipedia RAG Backend is running!", "version": "2.0.0"}`

2. **Interactive API docs:** Open `http://127.0.0.1:8001/docs`
   - You should see the Swagger UI with all endpoints

3. **Frontend:** Open `http://localhost:5173`
   - You should see the dark-themed AI Wikipedia Search UI

4. **End-to-end test:**
   - Type "Albert Einstein" in the search box and press Enter
   - Wait for the article card to appear
   - Type "What did Einstein discover?" in the AI question box
   - Click "Ask AI" and wait for the answer

If all four steps work, your installation is complete! 🎉

---

## Environment Variables Reference

Create `backend/.env` with the following variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | ✅ (if no Groq) | — | OpenRouter API key for fallback LLM |
| `GROQ_API_KEY` | ✅ (if no OpenRouter) | — | Groq API key for primary LLM (faster) |

The system gracefully handles missing keys:
- If `GROQ_API_KEY` is not set → uses OpenRouter directly
- If both are set → uses Groq with OpenRouter as fallback
- If neither is set → every `/ask` request returns a connection error

---

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'app'`

**Cause:** Running `uvicorn` from the wrong directory.

**Fix:** Run from the project root:
```bash
# Correct (from ai-wikipedia-rag/ root)
uvicorn backend.app.main:app --reload --port 8001

# Also correct (from backend/)
uvicorn app.main:app --reload --port 8001
```

---

### `OSError: [Errno 98] Address already in use`

**Cause:** Port 8001 is already in use.

**Fix:** Kill the process using port 8001:
```bash
# Windows
netstat -ano | findstr :8001
taskkill /PID <PID> /F

# macOS / Linux
lsof -ti:8001 | xargs kill -9
```

Or use a different port: `uvicorn backend.app.main:app --reload --port 8002` and update the frontend's fetch URL from `8001` to `8002`.

---

### `Failed to connect to backend. Is the server running?`

**Cause:** The React frontend can't reach the backend at `localhost:8001`.

**Fix:**
1. Confirm the backend is running: `curl http://127.0.0.1:8001/`
2. Check that the port matches: the backend default is `8001`, the frontend calls `http://127.0.0.1:8001`
3. Check for firewall blocking local connections

---

### Embedding model download fails

**Cause:** No internet connection, or HuggingFace is blocked.

**Fix:** The model is downloaded from `https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2`. Ensure internet access and try again. Once downloaded, it's cached locally at `~/.cache/huggingface/`.

---

### `GROQ_API_KEY not set — using OpenRouter directly`

This is **not an error** — it's an informational log message. The backend is working correctly, just using OpenRouter instead of Groq. To use Groq (faster), add your `GROQ_API_KEY` to `backend/.env`.

---

### Slow first response to `/ask`

**Cause:** The embedding model is loading for the first time (downloads ~22 MB from HuggingFace if not cached locally).

**Fix:** Normal behavior. Subsequent requests are much faster (model is loaded into memory).

---

### `npm: command not found`

**Cause:** Node.js is not installed.

**Fix:** Download and install Node.js LTS from [https://nodejs.org](https://nodejs.org).

---

## Updating Dependencies

### Backend

```bash
cd backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install --upgrade -r requirements.txt
```

### Frontend

```bash
cd frontend
npm update
```
