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

# Rate limiting (protección de fuerza bruta, sobre todo en /auth/login)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

import storage as _storage

# Local uploads dir — always created so the vision agent can write temp files.
os.makedirs(_storage.UPLOAD_DIR, exist_ok=True)

if not _storage.is_cloud():
    # In local dev serve files directly; in production they come from R2.
    app.mount("/uploads", StaticFiles(directory=_storage.UPLOAD_DIR), name="uploads")
else:
    logger.info(f"Cloud storage active (R2 bucket: {os.environ.get('S3_BUCKET_NAME')}). /uploads not mounted.")

# Configuración de CORS
# Configura CORS_ORIGINS como lista separada por comas en producción, p.ej:
# CORS_ORIGINS=https://tu-frontend.up.railway.app,https://otro-dominio.com
_cors_env = os.environ.get("CORS_ORIGINS", "*")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env != "*" else ["*"]

# Con orígenes comodín ("*") NO se pueden permitir credenciales (los navegadores
# lo rechazan y es un antipatrón). La app usa JWT por cabecera Authorization, no
# cookies, así que desactivar credentials en modo "*" es seguro y correcto.
_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes.auth import router as auth_router
from api.routes.estimates import router as estimates_router
from api.routes.holded import router as holded_router
from api.routes.knowledge import router as knowledge_router
from api.routes.workflow import router as workflow_router
from fastapi import Response
from fastapi.responses import StreamingResponse


@app.get("/")
def read_root():
    return {"status": "ok", "message": "API de Carpintería AI en funcionamiento"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/files/{filename:path}")
async def serve_file(filename: str):
    """
    Proxy endpoint for plan images.
    Tries local disk first, then falls back to R2 — no public bucket access required.
    """
    from fastapi import HTTPException
    try:
        result = await _storage.fetch(filename)
    except _storage.UnsafeFilenameError:
        # Intento de path traversal (p.ej. ../../etc/passwd)
        raise HTTPException(status_code=400, detail="Invalid filename")
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    data, mime = result
    # Los nombres son únicos e inmutables (uuid por estimate): el navegador puede
    # cachearlos — el visor no re-descarga las 11 páginas al navegar/recargar.
    return Response(
        content=data, media_type=mime,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


app.include_router(auth_router)
app.include_router(estimates_router)
app.include_router(holded_router)
app.include_router(knowledge_router)
app.include_router(workflow_router)

