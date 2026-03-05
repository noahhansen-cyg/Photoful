# Stage 1 — Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2 — Python app (serves API + built SPA + WebSocket)
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 5000

# gunicorn + geventwebsocket for WebSocket support.
# Single worker required (in-memory room state).
CMD ["sh", "-c", "cd backend && gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --timeout 120 --bind 0.0.0.0:${PORT:-5000} app:app"]
