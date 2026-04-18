"""
Entry point FastAPI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from rag.chroma_client import ChromaClient
from db.persistence import init_db, get_checkpointer

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
        async with get_checkpointer() as _:
            logger.info("Tablas de Checkpointer LangGraph verificadas/creadas.")
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

app = FastAPI(title="Carpintería AI API", lifespan=lifespan)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, se deben especificar los dominios permitidos (ej. frontend en localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API de Carpintería AI en funcionamiento"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/estimates")
def create_estimate():
    pass

@app.post("/resume")
def resume_workflow():
    pass
