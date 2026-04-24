import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv("POSTGRES_URL")

# --- Configuración de SQLAlchemy ---
if POSTGRES_URL:
    db_url = POSTGRES_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    engine = create_async_engine(db_url, echo=False)
else:
    engine = create_async_engine("sqlite+aiosqlite:///./local_dev.db", echo=False)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def init_db():
    """Inicializa las tablas de SQLAlchemy."""
    import db.models  # Import models here to register them with Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tablas de SQLAlchemy creadas/verificadas.")

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Generador de sesiones asíncronas para FastAPI."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

# --- Configuración del Checkpointer de LangGraph ---
# Pool global para evitar crear demasiadas conexiones a PostgreSQL
_pg_pool: Optional[AsyncConnectionPool] = None

@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator:
    """
    Obtiene el checkpointer de LangGraph.
    Si POSTGRES_URL está configurado, usa AsyncPostgresSaver.
    De lo contrario, usa AsyncSqliteSaver para desarrollo local.
    Crea las tablas automáticamente al arrancar (setup).
    """
    global _pg_pool
    
    if POSTGRES_URL:
        if _pg_pool is None:
            logger.info("Creando AsyncConnectionPool global para el checkpointer.")
            _pg_pool = AsyncConnectionPool(
                conninfo=POSTGRES_URL,
                min_size=1,
                max_size=20,
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            # Abrir el pool explícitamente para que esté listo
            await _pg_pool.open()
            
        checkpointer = AsyncPostgresSaver(_pg_pool)
        # Opcional: setup() solo es necesario una vez al inicio, pero es idempotente
        await checkpointer.setup()
        yield checkpointer
    else:
        logger.info("Usando AsyncSqliteSaver para el checkpointer local.")
        async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
            await checkpointer.setup()
            yield checkpointer

async def close_checkpointer_pool():
    """Cierra el pool global de conexiones de PostgreSQL al apagar la aplicación."""
    global _pg_pool
    if _pg_pool is not None:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("Pool global de AsyncConnectionPool cerrado.")
