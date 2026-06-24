# 📋 Deployment Checklist

## Pre-Deployment (Local Testing)

- [ ] Run `npm run build` in frontend directory (verify no errors)
- [ ] Run backend with `uvicorn backend.app.main:app --reload`
- [ ] Test the full application locally
- [ ] Commit and push all changes to GitHub

## Backend Setup (HuggingFace Spaces)

- [ ] Create HuggingFace account
- [ ] Create new Space with Docker SDK
- [ ] Connect GitHub repository to HF Space
- [ ] Add secrets in HF Space settings:
  - [ ] `GROQ_API_KEY`
  - [ ] `GEMINI_API_KEY`
  - [ ] `OPENROUTER_API_KEY`
  - [ ] `MINIMAX_API_KEY`
- [ ] Wait for Space to build and become "Running"
- [ ] Verify backend at: `https://your-username-ai-wikipedia-rag.hf.space/docs`
- [ ] Note down the Space URL

## Frontend Setup (Vercel)

- [ ] Create Vercel account
- [ ] Import GitHub repository to Vercel
- [ ] Configure environment variables:
  - [ ] `VITE_API_BASE_URL` = (your HF Space URL)
- [ ] Verify build succeeds
- [ ] Test frontend deployment URL
- [ ] Note down the Vercel URL

## Final Integration

- [ ] Update HF Space secret `FRONTEND_URL` with your Vercel URL
- [ ] Wait for HF Space to restart
- [ ] Test full integration:
  - [ ] Open frontend on Vercel
  - [ ] Search for an article
  - [ ] Ask a question
  - [ ] Verify response appears

## Post-Deployment

- [ ] Monitor HF Space logs for errors
- [ ] Check Vercel analytics/logs
- [ ] Test on mobile browser
- [ ] Share with team/users
- [ ] Set up monitoring/alerts (optional)

---

## Files Modified/Created for Deployment

- [vercel.json](../vercel.json) - Vercel configuration
- [.vercelignore](../.vercelignore) - Files to ignore for Vercel
- [frontend/.env.example](../frontend/.env.example) - Frontend env template
- [backend/.env.example](../backend/.env.example) - Backend env template
- [frontend/src/App.jsx](../frontend/src/App.jsx) - Updated API URL handling
- [backend/app/main.py](../backend/app/main.py) - Updated CORS configuration
- [Dockerfile](../Dockerfile) - HF Spaces backend configuration
- [docs/deployment.md](./deployment.md) - Full deployment guide

---

## Quick Links

- HuggingFace: https://huggingface.co
- Vercel: https://vercel.com
- Groq API: https://console.groq.com
- Gemini API: https://aistudio.google.com
- OpenRouter: https://openrouter.ai
- MiniMax: https://platform.minimax.io
