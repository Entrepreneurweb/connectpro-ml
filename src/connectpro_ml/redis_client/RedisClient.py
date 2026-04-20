
import logging

import redis.asyncio as redis

from connectpro_ml.persistence.configs.Config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


async def connect_redis() -> None:
    global _client
    _client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    await _client.ping()
    logger.info(" Connecté à Redis — %s", settings.REDIS_HOST)


async def close_redis() -> None:

    global _client
    if _client:
        await _client.close()
        _client = None
        logger.info(" Connexion Redis fermée")


def get_redis() -> redis.Redis:

    if _client is None:
        raise RuntimeError("Redis non connecté. Appelez connect_redis() d'abord.")
    return _client