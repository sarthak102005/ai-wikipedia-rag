# 🚀 Deployment Guide — Vercel Frontend + HuggingFace Spaces Backend

This guide walks you through deploying the AI Wikipedia RAG application on **Vercel** (frontend) and **HuggingFace Spaces** (backend) for the first time.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Part 1: Backend Deployment on HuggingFace Spaces](#part-1-backend-deployment-on-huggingface-spaces)
- [Part 2: Frontend Deployment on Vercel](#part-2-frontend-deployment-on-vercel)
- [Part 3: Connect Frontend to Backend](#part-3-connect-frontend-to-backend)
- [Environment Variables Reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you start, you'll need:

1. **GitHub Account** — Required for both Vercel and HF Spaces
2. **HuggingFace Account** — [Sign up here](https://huggingface.co/join)
3. **Vercel Account** — [Sign up here](https://vercel.com/signup)
4. **API Keys** for:
   - **Groq** (primary LLM) — [Get key](https://console.groq.com)
   - **Gemini** (fallback) — [Get key](https://aistudio.google.com)
   - **OpenRouter** (fallback) — [Get key](https://openrouter.ai)
   - **MiniMax** (fallback) — [Get key](https://platform.minimax.io)

---

## Part 1: Backend Deployment on HuggingFace Spaces

### Step 1.1: Push Code to GitHub

If you haven't already, push your repository to GitHub:

```bash
git add .
git commit -m "Prepare for deployment"
git push origin main
```

### Step 1.2: Create a HuggingFace Space

1. Go to [HuggingFace Spaces](https://huggingface.co/spaces)
2. Click **"Create new Space"**
3. Fill in the form:
   - **Space name:** `ai-wikipedia-rag` (or your preferred name)
   - **Space SDK:** Select **"Docker"**
   - **Visibility:** Public or Private (recommended: Private for testing)
4. Click **"Create Space"**

### Step 1.3: Connect Your GitHub Repository

After the Space is created:

1. Go to **Settings** → **"Sync with a Git repo"**
2. Connect your GitHub account and select your repository
3. Enable **"Auto sync"** (optional, but recommended)

The Space will now automatically pull from your GitHub repository and rebuild when you push changes.

### Step 1.4: Add Environment Variables (Secrets)

The Space will use the `Dockerfile` in your repository root. Before it starts, configure the API keys:

1. Go to **Settings** → **"Repository secrets"**
2. Add each API key as a secret:

   | Secret Name | Value |
   |---|---|
   | `GROQ_API_KEY` | Your Groq API key |
   | `GEMINI_API_KEY` | Your Gemini API key |
   | `OPENROUTER_API_KEY` | Your OpenRouter API key |
   | `MINIMAX_API_KEY` | Your MiniMax API key |
   | `FRONTEND_URL` | `https://your-frontend-domain.vercel.app` (add this after deploying frontend) |

3. Click **"Save"** for each secret

### Step 1.5: Verify Backend is Running

1. The Space should start building automatically
2. Monitor the **Build** tab to watch the Docker build progress
3. Once complete, you'll see a running status and a URL like:
   ```
   https://your-username-ai-wikipedia-rag.hf.space
   ```

4. Test the backend by visiting:
   ```
   https://your-username-ai-wikipedia-rag.hf.space/docs
   ```
   You should see the FastAPI interactive documentation.

---

## Part 2: Frontend Deployment on Vercel

### Step 2.1: Connect to Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click **"Add New Project"**
3. Select **"Import Git Repository"**
4. Paste your GitHub repository URL and click **"Import"**

### Step 2.2: Configure Build Settings

Vercel should auto-detect the settings, but ensure:

| Setting | Value |
|---|---|
| Framework Preset | **Vite** |
| Build Command | `cd frontend && npm install && npm run build` |
| Output Directory | `frontend/dist` |
| Install Command | (leave default) |

### Step 2.3: Add Environment Variables

1. Go to **Settings** → **"Environment Variables"**
2. Add the backend URL:

   ```
   VITE_API_BASE_URL = https://your-username-ai-wikipedia-rag.hf.space
   ```

3. Click **"Save"**

### Step 2.4: Deploy

1. Vercel will automatically deploy your frontend
2. Once complete, you'll get a URL like:
   ```
   https://ai-wikipedia-rag.vercel.app
   ```

3. Click the URL to verify the frontend loads correctly

---

## Part 3: Connect Frontend to Backend

### Step 3.1: Update Backend CORS

Now that you have your Vercel frontend URL, update the backend:

1. In your HuggingFace Space settings, update the `FRONTEND_URL` secret with your actual Vercel URL:
   ```
   https://ai-wikipedia-rag.vercel.app
   ```

2. The backend will automatically restart and add your frontend to the CORS whitelist

### Step 3.2: Test the Connection

1. Open your frontend: `https://ai-wikipedia-rag.vercel.app`
2. Search for a Wikipedia article
3. Ask a question about it

If it works, you're done! 🎉

---

## Environment Variables Reference

### Frontend (.env in Vercel)

```env
# Backend API URL (set in Vercel dashboard)
VITE_API_BASE_URL=https://your-username-ai-wikipedia-rag.hf.space
```

### Backend (.env in HuggingFace Spaces)

These are set as **Repository Secrets** in HF Spaces:

```env
# LLM API Keys
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AQ...
OPENROUTER_API_KEY=sk-or-...
MINIMAX_API_KEY=sk-api-...

# Frontend URL (for CORS)
FRONTEND_URL=https://ai-wikipedia-rag.vercel.app

# Server Config (auto-set by HF Spaces)
PORT=7860
PYTHONUNBUFFERED=1
```

---

## Troubleshooting

### Issue: Frontend shows "All configured AI models are unavailable"

**Cause:** Backend API keys are not set or frontend cannot connect to backend.

**Solution:**
1. Verify `VITE_API_BASE_URL` is set correctly in Vercel
2. Check that the backend URL is reachable: Visit `https://your-space.hf.space/docs`
3. Check HF Space logs (in the **Build** tab) for API key errors

### Issue: "CORS error" in browser console

**Cause:** Frontend URL not added to backend CORS whitelist.

**Solution:**
1. Update `FRONTEND_URL` secret in HF Spaces Settings
2. Wait for the Space to restart (1-2 minutes)
3. Refresh your browser

### Issue: Backend returns 503 (Service Unavailable)

**Cause:** HF Space is still building or out of memory.

**Solution:**
1. Check the **Build** tab in HF Spaces for errors
2. If it's a memory issue, you may need to upgrade the Space's hardware
3. Check the **Logs** tab for specific error messages

### Issue: "API key not set" errors in HF Space logs

**Cause:** Secret not properly saved.

**Solution:**
1. Go to HF Space **Settings** → **"Repository secrets"**
2. Delete and re-add the secret
3. Wait 30 seconds for it to register
4. Manually restart the Space (if available)

### Issue: Frontend works locally but not on Vercel

**Cause:** Environment variable not injected.

**Solution:**
1. Rebuild the Vercel deployment: **Settings** → **"Deployments"** → click the latest → **Redeploy**
2. Verify the build logs show the env var being used

---

## Optional: Custom Domain

### Add Custom Domain to Vercel Frontend

1. Vercel Dashboard → **Project Settings** → **Domains**
2. Add your domain and follow DNS configuration steps

### Add Custom Domain to HuggingFace Space

HF Spaces don't support custom domains directly, but you can:
- Use a reverse proxy (not recommended for beginners)
- Use the default HF Spaces URL

---

## Next Steps

- Monitor HF Space logs for errors
- Set up automatic alerts for API rate limits
- Consider caching strategy for frequently asked questions
- Plan for scaling if traffic increases

For more info, see:
- [HuggingFace Spaces Docs](https://huggingface.co/docs/hub/spaces)
- [Vercel Docs](https://vercel.com/docs)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
