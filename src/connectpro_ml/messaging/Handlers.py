
import logging

from connectpro_ml.persistence.Database import get_connection
from connectpro_ml.messaging import SyncRepository
from connectpro_ml.messaging import InteractionRepository
from connectpro_ml.embedding.EmbeddingWorker import enqueue_embedding
from connectpro_ml.flush.FlushWorker import check_and_flush

logger = logging.getLogger(__name__)


async def handle_sync_event(payload: dict, routing_key: str) -> None:

    event_type = payload.get("event_type", "")
    data = payload.get("data", {})
    version = payload.get("version", 1)

    logger.info(" Sync event — type=%s, version=%d", event_type, version)

    async with get_connection() as conn:

        if event_type == "category.created":
            await SyncRepository.upsert_category(conn, data)

        elif event_type in ("portfolio.created", "portfolio.updated"):
            await SyncRepository.upsert_portfolio(conn, data)
            enqueue_embedding("portfolio", data["id"])

        elif event_type in ("service.created", "service.updated"):
            await SyncRepository.upsert_service(conn, data)
            enqueue_embedding("service", data["id"])
        elif event_type == "service.deactivated":
            await SyncRepository.update_service_status(conn, data["id"], "inactive")
        elif event_type == "service.deleted":
            await SyncRepository.delete_service(conn, data["id"])

        elif event_type in ("job_post.created", "job_post.updated"):
            await SyncRepository.upsert_job_post(conn, data)
            enqueue_embedding("job_post", data["id"])
        elif event_type == "job_post.closed":
            await SyncRepository.update_job_post_status(conn, data["id"], "closed")

        elif event_type in ("review.created", "review.updated"):
            await SyncRepository.upsert_review(conn, data)

        else:
            logger.warning("Event type inconnu ignoré — %s", event_type)


async def handle_interaction_event(payload: dict, routing_key: str) -> None:

    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    logger.info(
        " Interaction event — type=%s, user=%s, item=%s",
        event_type,
        data.get("user_id", "?"),
        data.get("item_id", "?"),
    )

    async with get_connection() as conn:

        if event_type.startswith("user.interaction."):

            if data.get("interaction_type") == "dismiss":
                await InteractionRepository.insert_dismissed_item(conn, data)
            else:
                await InteractionRepository.insert_pending_interaction(conn, data)

                await check_and_flush(data["user_id"], data.get("interaction_type", ""))

        elif event_type == "user.follow.created":
            await InteractionRepository.insert_follow(conn, data)

        elif event_type == "user.follow.deleted":
            await InteractionRepository.delete_follow(conn, data)

        else:
            logger.warning(" Interaction event inconnu ignoré — %s", event_type)