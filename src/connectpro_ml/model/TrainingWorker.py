"""
Training worker  cron periodique qui entraine LightFM
et recharge le modele en memoire apres l'entrainement.
"""
import asyncio
import logging

from connectpro_ml.model.ModelTrainer import train_model
from connectpro_ml.model.ModelLoader import reload_if_updated

logger = logging.getLogger(__name__)


TRAINING_INTERVAL_SECONDS = 6 * 60 * 60

_worker_task: asyncio.Task | None = None


async def start_training_worker() -> None:

    global _worker_task
    _worker_task = asyncio.create_task(_training_loop())
    logger.info(
        "Training worker demarre -- intervalle=%dh",
        TRAINING_INTERVAL_SECONDS // 3600,
    )


async def stop_training_worker() -> None:

    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info("Training worker arrete")


async def _training_loop() -> None:

    await asyncio.sleep(60)
    await _run_training()

    while True:
        try:
            await asyncio.sleep(TRAINING_INTERVAL_SECONDS)
            await _run_training()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Erreur dans le cron d'entrainement")


async def _run_training() -> None:
    logger.info("Debut de l'entrainement periodique LightFM...")

    success = await train_model()

    if success:
        reload_if_updated()
        logger.info("Entrainement termine et modele recharge")
    else:
        logger.info("Entrainement ignore (pas assez de donnees)")