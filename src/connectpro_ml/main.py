import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(message)s",
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

from contextlib import asynccontextmanager
from fastapi import FastAPI

from connectpro_ml.persistence.Database import create_pool, close_pool
from connectpro_ml.persistence.Items import router as items_router
from connectpro_ml.messaging.RabbitMQ import connect_rabbitmq, disconnect_rabbitmq, start_consuming
from connectpro_ml.messaging.Handlers import handle_sync_event, handle_interaction_event
from connectpro_ml.embedding.EmbeddingService import load_model
from connectpro_ml.embedding.EmbeddingWorker import start_embedding_worker, stop_embedding_worker
from connectpro_ml.flush.FlushWorker import start_flush_worker, stop_flush_worker
from connectpro_ml.scoring.ScoringWorker import start_scoring_worker, stop_scoring_worker
from connectpro_ml.redis_client.RedisClient import connect_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    #  Startup
    await create_pool()
    await connect_redis()
    load_model()
    await start_embedding_worker()
    await start_flush_worker()
    await start_scoring_worker()
    await connect_rabbitmq()
    await start_consuming(
        on_sync_event=handle_sync_event,
        on_interaction_event=handle_interaction_event,
    )

    yield

    #  Fermeture
    await disconnect_rabbitmq()
    await stop_flush_worker()
    await stop_scoring_worker()
    await stop_embedding_worker()
    await close_redis()
    await close_pool()


app = FastAPI(title="Recommendation Service", lifespan=lifespan)
app.include_router(items_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}