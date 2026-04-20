
import json
import logging
from typing import Callable, Awaitable

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import (
    AbstractRobustConnection,
    AbstractRobustChannel,
    AbstractRobustQueue,
    AbstractIncomingMessage,
)

from connectpro_ml.persistence.configs.Config import settings

logger = logging.getLogger(__name__)


_connection: AbstractRobustConnection | None = None
_channel: AbstractRobustChannel | None = None
_sync_queue: AbstractRobustQueue | None = None
_interactions_queue: AbstractRobustQueue | None = None


async def connect_rabbitmq() -> None:

    global _connection, _channel, _sync_queue, _interactions_queue

    _connection = await aio_pika.connect_robust(
        settings.RABBITMQ_URL,
        client_properties={"connection_name": "reco-service"},
    )
    logger.info(" Connecté à RabbitMQ — %s", settings.RABBITMQ_HOST)

    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=settings.RABBITMQ_PREFETCH_COUNT)

    exchange = await _channel.declare_exchange(
        settings.RABBITMQ_EXCHANGE,
        type=ExchangeType.TOPIC,
        durable=True,
    )
    logger.info(" Exchange déclaré — %s (topic, durable)", settings.RABBITMQ_EXCHANGE)
    _sync_queue = await _channel.declare_queue(
        settings.RABBITMQ_SYNC_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": f"{settings.RABBITMQ_SYNC_QUEUE}.dlq",
        },
    )

    sync_bindings = [
        "service.*",
        "job_post.*",
        "portfolio.*",
        "category.*",
        "review.*",
    ]
    for binding in sync_bindings:
        await _sync_queue.bind(exchange, routing_key=binding)
    logger.info(" Queue %s — bindings: %s", settings.RABBITMQ_SYNC_QUEUE, sync_bindings)

    _interactions_queue = await _channel.declare_queue(
        settings.RABBITMQ_INTERACTIONS_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": f"{settings.RABBITMQ_INTERACTIONS_QUEUE}.dlq",
        },
    )
    interaction_bindings = [
        "user.interaction.*",
        "user.follow.*",
    ]
    for binding in interaction_bindings:
        await _interactions_queue.bind(exchange, routing_key=binding)
    logger.info(" Queue %s — bindings: %s", settings.RABBITMQ_INTERACTIONS_QUEUE, interaction_bindings)

    await _channel.declare_queue(f"{settings.RABBITMQ_SYNC_QUEUE}.dlq", durable=True)
    await _channel.declare_queue(f"{settings.RABBITMQ_INTERACTIONS_QUEUE}.dlq", durable=True)
    logger.info(" Dead letter queues déclarées")


async def disconnect_rabbitmq() -> None:

    global _connection, _channel
    if _connection:
        await _connection.close()
        _connection = None
        _channel = None
        logger.info(" Connexion RabbitMQ fermée")



async def start_consuming(
    on_sync_event: Callable[[dict, str], Awaitable[None]],
    on_interaction_event: Callable[[dict, str], Awaitable[None]],
) -> None:

    if not _sync_queue or not _interactions_queue:
        raise RuntimeError("RabbitMQ non connecté. Appelez connect_rabbitmq() d'abord.")

    async def _wrap_handler(
        message: AbstractIncomingMessage,
        handler: Callable[[dict, str], Awaitable[None]],
    ) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body.decode("utf-8"))
                routing_key = message.routing_key or ""
                logger.debug(
                    " Message reçu — routing_key=%s, event_type=%s",
                    routing_key,
                    payload.get("event_type", "unknown"),
                )
                await handler(payload, routing_key)
            except json.JSONDecodeError:
                logger.error(" Message non-JSON reçu, envoyé en DLQ — body=%s", message.body[:200])
                raise
            except Exception:
                logger.exception("Erreur handler — routing_key=%s", message.routing_key)
                raise

    await _sync_queue.consume(
        lambda msg: _wrap_handler(msg, on_sync_event)
    )
    logger.info(" Consumer démarré — %s", settings.RABBITMQ_SYNC_QUEUE)

    await _interactions_queue.consume(
        lambda msg: _wrap_handler(msg, on_interaction_event)
    )
    logger.info(" Consumer démarré — %s", settings.RABBITMQ_INTERACTIONS_QUEUE)