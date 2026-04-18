import os
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from psycopg_pool import AsyncConnectionPool

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tablas de SQLAlchemy creadas/verificadas.")

# --- Configuración del Checkpointer de LangGraph ---
@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator:
    """
    Obtiene el checkpointer de LangGraph.
    Si POSTGRES_URL está configurado, usa AsyncPostgresSaver.
    De lo contrario, usa AsyncSqliteSaver para desarrollo local.
    Crea las tablas automáticamente al arrancar (setup).
    """
    if POSTGRES_URL:
        logger.info("Usando AsyncPostgresSaver para el checkpointer.")
        async with AsyncConnectionPool(
            conninfo=POSTGRES_URL,
            max_size=20,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        ) as pool:
            checkpointer = AsyncPostgresSaver(pool)
            logger.info("Configurando tablas para AsyncPostgresSaver...")
            await checkpointer.setup()
            yield checkpointer
    else:
        logger.info("Usando AsyncSqliteSaver para el checkpointer local.")
        async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
            logger.info("Configurando tablas para AsyncSqliteSaver...")
            await checkpointer.setup()
            yield checkpointer
