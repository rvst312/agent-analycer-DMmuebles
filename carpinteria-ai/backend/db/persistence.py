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
    logger.info("DB: usando PostgreSQL (POSTGRES_URL definida)")
    db_url = POSTGRES_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(
        db_url,
        echo=False,
        pool_size=20,        # concurrent sessions
        max_overflow=10,     # burst headroom
        pool_pre_ping=True,  # detect stale connections
        pool_timeout=10,     # fail fast instead of blocking 30 s
        pool_recycle=300,    # refresh connections every 5 min
    )
else:
    logger.info("DB: usando SQLite local (POSTGRES_URL no definida)")
    engine = create_async_engine("sqlite+aiosqlite:///./local_dev.db", echo=False)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

def _apply_migrations(conn):
    """Add new columns to existing tables without dropping them (safe for any env)."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "presupuestos" not in tables:
        return  # Table doesn't exist yet — create_all handles creation

    existing = {c["name"] for c in inspector.get_columns("presupuestos")}
    is_pg = conn.dialect.name == "postgresql"
    ts_type = "TIMESTAMP WITHOUT TIME ZONE" if is_pg else "DATETIME"

    new_cols = {
        "image_path": "ALTER TABLE presupuestos ADD COLUMN image_path TEXT",
        "updated_at": f"ALTER TABLE presupuestos ADD COLUMN updated_at {ts_type}",
    }
    for col, sql in new_cols.items():
        if col not in existing:
            try:
                # SAVEPOINT isolates each DDL so a failure doesn't abort the
                # whole transaction and prevents other migrations from being lost.
                conn.execute(text("SAVEPOINT _mig"))
                conn.execute(text(sql))
                conn.execute(text("RELEASE SAVEPOINT _mig"))
                logger.info(f"Migration: added column presupuestos.{col}")
            except Exception as e:
                try:
                    conn.execute(text("ROLLBACK TO SAVEPOINT _mig"))
                except Exception:
                    pass
                logger.warning(f"Migration skipped for {col}: {e}")


async def init_db():
    """Inicializa las tablas de SQLAlchemy y aplica migraciones de columnas."""
    import db.models  # Import models here to register them with Base
    async with engine.begin() as conn:
        # 1. Add missing columns to existing tables BEFORE create_all
        await conn.run_sync(_apply_migrations)
        # 2. Create any table that doesn't exist yet
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
# Both are global so setup() runs only once per process lifetime.
_pg_pool: Optional[AsyncConnectionPool] = None
_checkpointer_setup_done: bool = False


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator:
    """
    Obtiene el checkpointer de LangGraph.
    Si POSTGRES_URL está configurado, usa AsyncPostgresSaver.
    De lo contrario, usa AsyncSqliteSaver para desarrollo local.
    setup() se ejecuta una sola vez al arrancar para no desperdiciar conexiones.
    """
    global _pg_pool, _checkpointer_setup_done

    if POSTGRES_URL:
        if _pg_pool is None:
            logger.info("Creando AsyncConnectionPool global para el checkpointer.")
            _pg_pool = AsyncConnectionPool(
                conninfo=POSTGRES_URL,
                min_size=2,
                max_size=20,
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            await _pg_pool.open()

        checkpointer = AsyncPostgresSaver(_pg_pool)
        if not _checkpointer_setup_done:
            await checkpointer.setup()
            _checkpointer_setup_done = True
        yield checkpointer
    else:
        logger.info("Usando AsyncSqliteSaver para el checkpointer local.")
        async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
            if not _checkpointer_setup_done:
                await checkpointer.setup()
                _checkpointer_setup_done = True
            yield checkpointer

async def close_checkpointer_pool():
    """Cierra el pool global de conexiones de PostgreSQL al apagar la aplicación."""
    global _pg_pool
    if _pg_pool is not None:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("Pool global de AsyncConnectionPool cerrado.")
