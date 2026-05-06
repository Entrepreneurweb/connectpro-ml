
import asyncio
import logging
from dataclasses import dataclass

from connectpro_ml.persistence.Database import get_connection
from connectpro_ml.embedding.EmbeddingService import (
    compute_embedding,
    build_service_text,
    build_portfolio_text,
    build_job_post_text,
    EMBEDDING_VERSION,
)

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingJob:
    entity_type: str  # 'service' | 'portfolio' | 'job_post'
    entity_id: str



_queue: asyncio.Queue[EmbeddingJob] | None = None
_worker_task: asyncio.Task | None = None


async def start_embedding_worker() -> None:

    global _queue, _worker_task

    _queue = asyncio.Queue()
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info(" Embedding worker démarré")


async def stop_embedding_worker() -> None:

    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info("Embedding worker arrêté")


def enqueue_embedding(entity_type: str, entity_id: str) -> None:

    if _queue is None:
        logger.warning("Embedding worker non démarré, job ignoré — %s:%s", entity_type, entity_id)
        return

    job = EmbeddingJob(entity_type=entity_type, entity_id=entity_id)
    _queue.put_nowait(job)
    logger.debug(" Embedding job enqueued — %s:%s (queue size: %d)", entity_type, entity_id, _queue.qsize())



# Worker loop

async def _worker_loop() -> None:
    logger.info(" Embedding worker loop started")

    while True:
        try:
            job = await _queue.get()

            try:
                await _process_job(job)
            except Exception:
                logger.exception(" Erreur embedding — %s:%s", job.entity_type, job.entity_id)
            finally:
                _queue.task_done()

        except asyncio.CancelledError:
            logger.info(" Embedding worker loop cancelled, processing remaining jobs...")
            # Traiter les jobs restants avant de quitter
            while not _queue.empty():
                job = _queue.get_nowait()
                try:
                    await _process_job(job)
                except Exception:
                    logger.exception(" Erreur embedding (shutdown) — %s:%s", job.entity_type, job.entity_id)
                _queue.task_done()
            raise


async def _process_job(job: EmbeddingJob) -> None:

    if job.entity_type == "service":
        await _embed_service(job.entity_id)
    elif job.entity_type == "portfolio":
        await _embed_portfolio(job.entity_id)
    elif job.entity_type == "job_post":
        await _embed_job_post(job.entity_id)
    else:
        logger.warning("Entity type inconnu — %s", job.entity_type)




async def _embed_service(service_id: str) -> None:
    async with get_connection() as conn:

        row = await conn.fetchrow(
            """
            SELECT s.title, s.description, c.value as category_name
            FROM services s
            LEFT JOIN categories c ON c.id = s.category_id
            WHERE s.id = $1
            """,
            service_id,
        )
        if not row:
            logger.warning(" Service introuvable pour embedding — id=%s", service_id)
            return


        tag_rows = await conn.fetch(
            "SELECT value FROM service_tags WHERE service_id = $1",
            service_id,
        )
        tags = [r["value"] for r in tag_rows]


        faq_rows = await conn.fetch(
            "SELECT question, answer FROM service_faqs WHERE service_id = $1",
            service_id,
        )
        faqs = [{"question": r["question"], "answer": r["answer"]} for r in faq_rows]

        text = build_service_text(
            title=row["title"],
            description=row["description"],
            tags=tags,
            category_name=row["category_name"],
            faqs=faqs,
        )
        embedding_bytes = compute_embedding(text)

        await conn.execute(
            """
            UPDATE services
            SET embedding = $1, embedding_version = $2
            WHERE id = $3 AND embedding IS NULL
            """,
            embedding_bytes,
            EMBEDDING_VERSION,
            service_id,
        )

    logger.info(" Service embedding calculé — id=%s, text_length=%d", service_id, len(text))


async def _embed_portfolio(portfolio_id: str) -> None:
    async with get_connection() as conn:

        row = await conn.fetchrow(
            "SELECT headline, bio FROM portfolios WHERE id = $1",
            portfolio_id,
        )
        if not row:
            logger.warning(" Portfolio introuvable pour embedding — id=%s", portfolio_id)
            return

        skill_rows = await conn.fetch(
            "SELECT skill FROM portfolio_skills WHERE portfolio_id = $1",
            portfolio_id,
        )
        skills = [r["skill"] for r in skill_rows]

        exp_rows = await conn.fetch(
            "SELECT role, company, description FROM portfolio_experiences WHERE portfolio_id = $1",
            portfolio_id,
        )
        experiences = [
            {"role": r["role"], "company": r["company"], "description": r["description"]}
            for r in exp_rows
        ]

        text = build_portfolio_text(
            headline=row["headline"],
            bio=row["bio"],
            skills=skills,
            experiences=experiences,
        )

        if not text.strip():
            logger.warning(" Portfolio texte vide, pas d'embedding — id=%s", portfolio_id)
            return

        embedding_bytes = compute_embedding(text)

        await conn.execute(
            """
            UPDATE portfolios
            SET profile_embedding = $1, embedding_version = $2
            WHERE id = $3 AND profile_embedding IS NULL
            """,
            embedding_bytes,
            EMBEDDING_VERSION,
            portfolio_id,
        )

    logger.info(" Portfolio embedding calculé — id=%s, text_length=%d", portfolio_id, len(text))


async def _embed_job_post(job_post_id: str) -> None:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT title, description FROM job_posts WHERE id = $1",
            job_post_id,
        )
        if not row:
            logger.warning(" JobPost introuvable pour embedding — id=%s", job_post_id)
            return

        text = build_job_post_text(title=row["title"], description=row["description"])
        embedding_bytes = compute_embedding(text)

        await conn.execute(
            """
            UPDATE job_posts
            SET embedding = $1, embedding_version = $2
            WHERE id = $3 AND embedding IS NULL
            """,
            embedding_bytes,
            EMBEDDING_VERSION,
            job_post_id,
        )

    logger.info(" JobPost embedding calculé — id=%s, text_length=%d", job_post_id, len(text))