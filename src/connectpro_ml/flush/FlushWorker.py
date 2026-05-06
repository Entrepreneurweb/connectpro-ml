
import asyncio
import logging

from connectpro_ml.persistence.Database import get_connection
from connectpro_ml.flush.FlushService import flush_user

logger = logging.getLogger(__name__)


VOLUME_THRESHOLD = 10
TIME_THRESHOLD_MINUTES = 1 #30
CRON_INTERVAL_SECONDS = 30 #300


HIGH_SIGNAL_TYPES = {"apply", "purchase", "contact", "quote_request"}

_worker_task: asyncio.Task | None = None


async def start_flush_worker() -> None:
    global _worker_task
    _worker_task = asyncio.create_task(_periodic_flush_loop())
    logger.info(" Flush worker démarré — interval=%ds", CRON_INTERVAL_SECONDS)


async def stop_flush_worker() -> None:

    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info(" Flush worker arrêté")


async def check_and_flush(user_id: str, interaction_type: str) -> None:


    if interaction_type in HIGH_SIGNAL_TYPES:
        logger.info(" Signal fort détecté (%s) — flush immédiat pour user=%s", interaction_type, user_id)
        await flush_user(user_id)
        return

    async with get_connection() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM pending_interactions WHERE user_id = $1",
            user_id,
        )

        if count >= VOLUME_THRESHOLD:
            logger.info(" Seuil de volume atteint (%d) — flush pour user=%s", count, user_id)
            await flush_user(user_id)
            return

        # Condition 3 : seuil de temps
        oldest = await conn.fetchval(
            "SELECT MIN(received_at) FROM pending_interactions WHERE user_id = $1",
            user_id,
        )

        if oldest:
            from datetime import datetime, timezone
            age_minutes = (datetime.now(timezone.utc) - oldest).total_seconds() / 60

            if age_minutes >= TIME_THRESHOLD_MINUTES:
                logger.info(" Seuil de temps atteint (%.0f min) — flush pour user=%s", age_minutes, user_id)
                await flush_user(user_id)
                return

async def _periodic_flush_loop() -> None:
     while True:
        try:
            await asyncio.sleep(CRON_INTERVAL_SECONDS)
            await _flush_stale_users()
        except asyncio.CancelledError:

            logger.info(" Flush worker shutdown — traitement des interactions restantes...")
            await _flush_all_pending()
            raise
        except Exception:
            logger.exception(" Erreur dans le cron de flush")


# async def _flush_stale_users() -> None:
#     async with get_connection() as conn:
#         stale_users = await conn.fetch(
#             """
#             SELECT DISTINCT user_id
#             FROM pending_interactions
#             WHERE received_at < NOW() - INTERVAL '$1 minutes'
#             """,
#             TIME_THRESHOLD_MINUTES,
#         )
#
#     if not stale_users:
#         return
#
#     logger.info(" Cron flush — %d users à traiter", len(stale_users))
#
#     for row in stale_users:
#         try:
#             await flush_user(row["user_id"])
#         except Exception:
#             logger.exception(" Erreur flush cron — user=%s", row["user_id"])

async def _flush_stale_users() -> None:
    async with get_connection() as conn:
        stale_users = await conn.fetch(
            """
            SELECT DISTINCT user_id
            FROM pending_interactions
            WHERE received_at < NOW() - INTERVAL '30 minutes'
            """,
        )

    if not stale_users:
        return

    logger.info(" Cron flush — %d users à traiter", len(stale_users))

    for row in stale_users:
        try:
            await flush_user(row["user_id"])
        except Exception:
            logger.exception(" Erreur flush cron — user=%s", row["user_id"])


async def _flush_all_pending() -> None:
    async with get_connection() as conn:
        all_users = await conn.fetch(
            "SELECT DISTINCT user_id FROM pending_interactions"
        )

    for row in all_users:
        try:
            await flush_user(row["user_id"])
        except Exception:
            logger.exception(" Erreur flush shutdown — user=%s", row["user_id"])