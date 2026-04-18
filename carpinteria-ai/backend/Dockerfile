# Dockerfile para el backend
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias (por ejemplo, para psycopg2 si es necesario)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
