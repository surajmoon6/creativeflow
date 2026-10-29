# Stage 1: build the React app
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Flask API + the built app, served by gunicorn
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /app/frontend/dist frontend/dist
ENV FRONTEND_DIST=/app/frontend/dist DATABASE_URL=sqlite:////data/creativeflow.db STORAGE_DIR=/data/storage TRUST_PROXY=1
VOLUME /data
WORKDIR /app/backend
EXPOSE 8000
# One worker with threads: rate limits are kept in-process, so a single process keeps them accurate.
CMD ["gunicorn", "-w", "1", "--threads", "8", "--timeout", "120", "-b", "0.0.0.0:8000", "wsgi:app"]
