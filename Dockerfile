# Stage 1: Build the React frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Run the FastAPI backend
FROM python:3.11-slim
WORKDIR /workspace

# Install system dependencies if any are needed (e.g. for building packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy root requirements.txt (which contains fastapi, uvicorn, sentence-transformers, faiss-cpu, etc.)
COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# Copy backend source code
COPY backend/ /workspace/backend/

# Copy built frontend assets
COPY --from=frontend-builder /frontend/dist /workspace/frontend/dist

# Ensure the backend data directory exists and has wide write permissions for Hugging Face Spaces
RUN mkdir -p /workspace/backend/data && chmod -R 777 /workspace/backend/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Expose port 7860 (Hugging Face default)
EXPOSE 7860

# Start uvicorn
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
