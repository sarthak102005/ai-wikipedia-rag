# ⚡ Quick Start: Deploy in 10 Minutes

**First time deploying?** Follow these 3 main steps.

---

## Step 1: Prepare API Keys (5 min)

Get these 4 free API keys:

1. **Groq** → https://console.groq.com/keys
2. **Gemini** → https://aistudio.google.com/apikey
3. **OpenRouter** → https://openrouter.ai/settings/keys
4. **MiniMax** → https://platform.minimax.io (sign up → create API key)

Save these keys somewhere safe (Notepad, 1Password, etc.). You'll need them shortly.

---

## Step 2: Deploy Backend to HuggingFace Spaces (3 min)

1. Go to https://huggingface.co/spaces
2. Click **"Create new Space"**
3. Fill in:
   - **Space name:** `ai-wikipedia-rag`
   - **SDK:** Docker
   - **Visibility:** Public or Private
4. Click **"Create Space"** and wait for it to load
5. Go to **Settings** → **"Repository secrets"**
6. Add your 4 API keys here:
   - `GROQ_API_KEY` = (your key)
   - `GEMINI_API_KEY` = (your key)
   - `OPENROUTER_API_KEY` = (your key)
   - `MINIMAX_API_KEY` = (your key)
7. Space will build automatically. Wait for it to say "Running" (2-3 min)
8. **Copy your Space URL** (looks like `https://username-ai-wikipedia-rag.hf.space`)

---

## Step 3: Deploy Frontend to Vercel (2 min)

1. Go to https://vercel.com/new
2. Import your GitHub repository
3. Set environment variable:
   - `VITE_API_BASE_URL` = (paste your HF Space URL from Step 2)
4. Click **"Deploy"** and wait (1-2 min)
5. **Copy your Vercel URL** (looks like `https://ai-wikipedia-rag.vercel.app`)

---

## Step 4: Final Connection (1 min)

Go back to your HF Space:
1. **Settings** → **Repository secrets**
2. Add (or update):
   - `FRONTEND_URL` = (paste your Vercel URL from Step 3)
3. Space will restart automatically

---

## Done! 🎉

Open your Vercel frontend URL and start using the app!

If something doesn't work, see [Full Deployment Guide](../docs/deployment.md) for troubleshooting.

---

## Useful URLs

- **Your Frontend:** https://your-project.vercel.app
- **Your Backend:** https://your-username-ai-wikipedia-rag.hf.space
- **Backend Docs:** https://your-username-ai-wikipedia-rag.hf.space/docs

---

## Files Changed for Deployment

✅ `Dockerfile` - Already configured for HF Spaces  
✅ `vercel.json` - Tells Vercel how to build  
✅ `.vercelignore` - Tells Vercel what to ignore  
✅ `frontend/src/App.jsx` - Updated to read backend URL from env var  
✅ `backend/app/main.py` - Updated CORS for production  
✅ `frontend/.env.example` - Shows required env vars for frontend  
✅ `backend/.env.example` - Shows required secrets for backend  

Everything is already set up. You just need to add the secrets!
