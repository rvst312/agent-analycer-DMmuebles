"""
Entry point FastAPI
"""
import logging
import os
from contextlib import asynccontextmanager

from db.persistence import close_checkpointer_pool, get_checkpointer, init_db
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rag.chroma_client import ChromaClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar tablas de SQLAlchemy
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")

    # Configurar tablas de Checkpointer de LangGraph
    try:
        # Esto inicializará y abrirá el pool global en el startup
        async with get_checkpointer() as checkpointer:
            logger.info("Tablas de Checkpointer LangGraph verificadas/creadas y pool inicializado.")
    except Exception as e:
        logger.error(f"Error al inicializar el Checkpointer: {e}")

    # Inicializar colecciones de ChromaDB al arrancar
    logger.info("Inicializando ChromaDB PersistentClient...")
    try:
        chroma_client = ChromaClient()
        collections = chroma_client.init_collections()
        logger.info(f"Colecciones de ChromaDB inicializadas: {collections}")
    except Exception as e:
        logger.error(f"Error al inicializar ChromaDB: {e}")
    yield
    # Limpieza al apagar (si es necesaria)
    logger.info("Apagando API...")
    try:
        await close_checkpointer_pool()
    except Exception as e:
        logger.error(f"Error al cerrar pool de checkpointer: {e}")

app = FastAPI(title="Carpintería AI API", lifespan=lifespan)

# Persistent upload directory — configurable via UPLOAD_DIR env var (mounted volume in Docker)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Configuración de CORS
# Configura CORS_ORIGINS como lista separada por comas en producción, p.ej:
# CORS_ORIGINS=https://tu-frontend.up.railway.app,https://otro-dominio.com
_cors_env = os.environ.get("CORS_ORIGINS", "*")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes.estimates import router as estimates_router
from api.routes.holded import router as holded_router
from api.routes.knowledge import router as knowledge_router
from api.routes.workflow import router as workflow_router


@app.get("/")
def read_root():
    return {"status": "ok", "message": "API de Carpintería AI en funcionamiento"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

app.include_router(estimates_router)
app.include_router(holded_router)
app.include_router(knowledge_router)
app.include_router(workflow_router)

