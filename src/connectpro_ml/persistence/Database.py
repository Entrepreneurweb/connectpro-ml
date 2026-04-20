
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
 
import asyncpg
from asyncpg import Pool, Connection

from connectpro_ml.persistence.configs.Config import settings

logger = logging.getLogger(__name__)
 
 

_pool: Pool | None = None
 
 
async def create_pool() -> Pool:

    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        max_inactive_connection_lifetime=settings.DB_POOL_MAX_INACTIVE_LIFETIME,
        command_timeout=settings.DB_COMMAND_TIMEOUT,

        max_queries=50_000,

        statement_cache_size=100,
        init=_init_connection,
    )
    logger.info(
        "Pool PostgreSQL créé — min=%d max=%d",
        settings.DB_POOL_MIN_SIZE,
        settings.DB_POOL_MAX_SIZE,
    )
    return _pool
 
 
async def close_pool() -> None:

    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info(" Pool PostgreSQL fermé.")
 
 
def get_pool() -> Pool:

    if _pool is None:
        raise RuntimeError("Le pool PostgreSQL n'est pas initialisé.")
    return _pool
 

async def _init_connection(conn: Connection) -> None:

    await conn.execute("SET search_path TO public")
    await conn.set_type_codec(
        "jsonb",
        encoder=lambda v: v,
        decoder=lambda v: v,
        schema="pg_catalog",
        format="text",
    )

 
@asynccontextmanager
async def get_connection() -> AsyncGenerator[Connection, None]:

    async with get_pool().acquire() as conn:
        yield conn
 
 
async def db_dependency() -> AsyncGenerator[Connection, None]:

    async with get_pool().acquire() as conn:
        yield conn
 

 
@asynccontextmanager
async def transaction(conn: Connection):

    async with conn.transaction():
        try:
            yield conn
        except Exception:
            logger.exception(" Transaction annulée (rollback)")
            raise
 