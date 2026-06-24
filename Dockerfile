# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Run the FastAPI backend
FROM python:3.12-slim
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /workspace/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r /workspace/requirements.txt

COPY backend/ /workspace/backend/
COPY --from=frontend-builder /frontend/dist /workspace/frontend/dist

RUN mkdir -p /workspace/backend/data && chmod -R 777 /workspace/backend/data

ENV PYTHONUNBUFFERED=1
ENV PORT=7860
ENV PYTHONPATH=/workspace/backend

EXPOSE 7860

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
