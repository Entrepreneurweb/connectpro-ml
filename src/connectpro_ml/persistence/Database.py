"""
Database configuration & pool manager — asyncpg
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
 
import asyncpg
from asyncpg import Pool, Connection

from connectpro_ml.persistence.configs.Config import settings

#from app.core.config import settings

 
logger = logging.getLogger(__name__)
 
 
# ---------------------------------------------------------------------------
# Pool singleton
# ---------------------------------------------------------------------------
 
_pool: Pool | None = None
 
 
async def create_pool() -> Pool:
    """Crée et retourne le pool de connexions PostgreSQL."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        max_inactive_connection_lifetime=settings.DB_POOL_MAX_INACTIVE_LIFETIME,
        command_timeout=settings.DB_COMMAND_TIMEOUT,
        # Ping la DB à chaque acquire pour détecter les connexions mortes
        max_queries=50_000,
        # Statement cache par connexion (améliore les perfs sur requêtes répétées)
        statement_cache_size=100,
        init=_init_connection,
    )
    logger.info(
        "✅ Pool PostgreSQL créé — min=%d max=%d",
        settings.DB_POOL_MIN_SIZE,
        settings.DB_POOL_MAX_SIZE,
    )
    return _pool
 
 
async def close_pool() -> None:
    """Ferme proprement le pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("🔌 Pool PostgreSQL fermé.")
 
 
def get_pool() -> Pool:
    """Retourne le pool existant (doit être initialisé au démarrage)."""
    if _pool is None:
        raise RuntimeError("Le pool PostgreSQL n'est pas initialisé.")
    return _pool
 
 
# ---------------------------------------------------------------------------
# Initialisation d'une connexion (appelé à chaque nouvelle connexion du pool)
# ---------------------------------------------------------------------------
 
async def _init_connection(conn: Connection) -> None:
    """
    Hook appelé à chaque création de connexion dans le pool.
    Idéal pour : SET search_path, enregistrer des codecs custom, etc.
    """
    await conn.execute("SET search_path TO public")
    # Exemple : codec JSON automatique
    await conn.set_type_codec(
        "jsonb",
        encoder=lambda v: v,   # remplacer par json.dumps si besoin
        decoder=lambda v: v,
        schema="pg_catalog",
        format="text",
    )
 
 
# ---------------------------------------------------------------------------
# Dependency FastAPI
# ---------------------------------------------------------------------------
 
@asynccontextmanager
async def get_connection() -> AsyncGenerator[Connection, None]:
    """Context manager — acquiert une connexion depuis le pool."""
    async with get_pool().acquire() as conn:
        yield conn
 
 
async def db_dependency() -> AsyncGenerator[Connection, None]:
    """
    Dependency injectable dans les routes FastAPI.
 
    Usage:
        @router.get("/")
        async def route(conn: Connection = Depends(db_dependency)):
            ...
    """
    async with get_pool().acquire() as conn:
        yield conn
 
 
# ---------------------------------------------------------------------------
# Helpers transactionnels
# ---------------------------------------------------------------------------
 
@asynccontextmanager
async def transaction(conn: Connection):
    """Wrapper transaction avec rollback automatique en cas d'erreur."""
    async with conn.transaction():
        try:
            yield conn
        except Exception:
            logger.exception("❌ Transaction annulée (rollback)")
            raise
 