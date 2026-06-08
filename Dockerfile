FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY data/ontology_grnti.json ./data/ontology_grnti.json

RUN mkdir -p /app/data/snapshots

ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
