# Dockerfile para el backend
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias (por ejemplo, para psycopg2 si es necesario)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the ChromaDB embedding model so the first estimate doesn't stall for 30s
RUN python3 -c 'from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(["warm up"])'

COPY backend/ .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
