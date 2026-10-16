# Stage 1: build the React app (Vite 8 needs Node 20.19+ or 22.12+)
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI serves the API and the built app; no torch, no GPU
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt
COPY backend/ .
COPY --from=web /web/dist /frontend/dist
# ponytail: the one demo clip is baked in (data/ can't go in git); a second video needs object storage
COPY ["data/videos/vlc-record-2026-10-11-12h12m18s-CS229-lecture02.mp4-.mp4", "/data/videos/"]
ENV FRONTEND_DIST=/frontend/dist VIDEO_DIR=/data/videos
# Render sets $PORT; compose and local runs fall back to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
