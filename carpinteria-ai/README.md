# Carpintería AI

Sistema de automatización de presupuestos de carpintería técnica.

## Instalación y Arranque

### Requisitos Previos
- Docker y Docker Compose
- Python 3.10+
- Node.js 18+

### Configuración
1. Clona el repositorio.
2. Copia el archivo de variables de entorno:
   ```bash
   cd backend
   cp .env.example .env
   ```
3. Configura tus claves de API en el archivo `.env` (Anthropic, Holded, webhooks, etc.).

### Arranque con Docker (Recomendado)
Para levantar todos los servicios (Backend, PostgreSQL, ChromaDB):
```bash
docker-compose up -d
```

### Arranque en Desarrollo (Manual)

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
El servidor de desarrollo estará disponible en `http://localhost:8000`.

#### Frontend
*(Requiere inicializar el proyecto Next.js en la carpeta frontend/)*
```bash
cd frontend
npm install
npm run dev
```
El frontend estará disponible en `http://localhost:3000`.
