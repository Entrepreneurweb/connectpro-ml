import asyncio
import logging
from dataclasses import dataclass

from connectpro_ml.scoring.ScoringService import compute_feed
from connectpro_ml.redis_client.FeedWriter import write_user_feed

logger = logging.getLogger(__name__)


@dataclass
class ScoringJob:
    user_id: str
    reason: str  # 'flush' | 'batch' | 'manual'


_queue: asyncio.Queue[ScoringJob] | None = None
_worker_task: asyncio.Task | None = None


async def start_scoring_worker() -> None:

    global _queue, _worker_task

    _queue = asyncio.Queue()
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info(" Scoring worker démarré")


async def stop_scoring_worker() -> None:

    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info(" Scoring worker arrêté")


def enqueue_scoring(user_id: str, reason: str = "flush") -> None:

    if _queue is None:
        logger.warning(" Scoring worker non démarré, job ignoré — user=%s", user_id)
        return

    job = ScoringJob(user_id=user_id, reason=reason)
    _queue.put_nowait(job)
    logger.debug(" Scoring job enqueued — user=%s, reason=%s (queue size: %d)", user_id, reason, _queue.qsize())


async def _worker_loop() -> None:

    logger.info(" Scoring worker loop started")

    while True:
        try:
            job = await _queue.get()

            try:
                await _process_job(job)
            except Exception:
                logger.exception(" Erreur scoring — user=%s", job.user_id)
            finally:
                _queue.task_done()

        except asyncio.CancelledError:
            logger.info(" Scoring worker shutdown — traitement des jobs restants...")
            while not _queue.empty():
                job = _queue.get_nowait()
                try:
                    await _process_job(job)
                except Exception:
                    logger.exception(" Erreur scoring (shutdown) — user=%s", job.user_id)
                _queue.task_done()
            raise


async def _process_job(job: ScoringJob) -> None:

    feed = await compute_feed(job.user_id)
    await write_user_feed(job.user_id, feed)
    logger.info(
        " Feed recalculé — user=%s, items=%d, reason=%s",
        job.user_id, len(feed), job.reason,
    )