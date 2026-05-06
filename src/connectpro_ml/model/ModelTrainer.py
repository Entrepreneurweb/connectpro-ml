"""
Model trainer  entraine le modele LightFM sur les interactions
et features, puis sauvegarde sur disque.
"""
import logging
import os
import pickle
import time
from pathlib import Path

from lightfm import LightFM

from connectpro_ml.model.FeatureBuilder import build_training_data, TrainingData

logger = logging.getLogger(__name__)

MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "lightfm_model.pkl"
TRAINING_DATA_PATH = MODEL_DIR / "training_data.pkl"


NO_COMPONENTS = 64
LEARNING_RATE = 0.05
LOSS = "warp"
EPOCHS = 30
NUM_THREADS = 2


async def train_model() -> bool:

    start = time.monotonic()


    training_data = await build_training_data()
    if training_data is None:
        logger.warning("Pas assez de donnees pour entrainer le modele")
        return False

    n_interactions = training_data.interactions.nnz
    if n_interactions < 10:
        logger.warning(
            "Trop peu d'interactions (%d), entrainement reporte", n_interactions
        )
        return False

    logger.info(
        "Debut de l'entrainement LightFM -- interactions=%d, loss=%s, components=%d, epochs=%d",
        n_interactions, LOSS, NO_COMPONENTS, EPOCHS,
    )


    model = LightFM(
        no_components=NO_COMPONENTS,
        learning_rate=LEARNING_RATE,
        loss=LOSS,
    )

    model.fit(
        interactions=training_data.interactions,
        item_features=training_data.item_features,
        user_features=training_data.user_features,
        epochs=EPOCHS,
        num_threads=NUM_THREADS,
        verbose=False,
    )


    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    with open(TRAINING_DATA_PATH, "wb") as f:
        pickle.dump({
            "user_id_map": training_data.user_id_map,
            "item_id_map": training_data.item_id_map,
            "reverse_user_map": training_data.reverse_user_map,
            "reverse_item_map": training_data.reverse_item_map,
            "item_features": training_data.item_features,
            "user_features": training_data.user_features,
            "item_feature_names": training_data.item_feature_names,
            "user_feature_names": training_data.user_feature_names,
        }, f)

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "Entrainement termine -- duration=%dms, modele sauvegarde dans %s",
        duration_ms, MODEL_PATH,
    )

    return True