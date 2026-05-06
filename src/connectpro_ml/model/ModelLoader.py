"""
Model loader — charge le modele LightFM depuis le disque,
le maintient en memoire, et fournit les predictions.
"""
import logging
import os
import pickle
from pathlib import Path

import numpy as np
from lightfm import LightFM

logger = logging.getLogger(__name__)

MODEL_PATH = Path("models/lightfm_model.pkl")
TRAINING_DATA_PATH = Path("models/training_data.pkl")


_model: LightFM | None = None
_user_id_map: dict[str, int] = {}
_item_id_map: dict[str, int] = {}
_reverse_user_map: dict[int, str] = {}
_reverse_item_map: dict[int, str] = {}
_item_features = None
_user_features = None
_model_mtime: float = 0.0


def load_model() -> bool:

    global _model, _user_id_map, _item_id_map, _reverse_user_map, _reverse_item_map
    global _item_features, _user_features, _model_mtime

    if not MODEL_PATH.exists() or not TRAINING_DATA_PATH.exists():
        logger.info("Aucun modele LightFM trouve sur le disque")
        return False

    current_mtime = os.path.getmtime(MODEL_PATH)
    if current_mtime == _model_mtime and _model is not None:
        return True

    with open(MODEL_PATH, "rb") as f:
        _model = pickle.load(f)

    with open(TRAINING_DATA_PATH, "rb") as f:
        data = pickle.load(f)
        _user_id_map = data["user_id_map"]
        _item_id_map = data["item_id_map"]
        _reverse_user_map = data["reverse_user_map"]
        _reverse_item_map = data["reverse_item_map"]
        _item_features = data["item_features"]
        _user_features = data["user_features"]

    _model_mtime = current_mtime
    logger.info(
        "Modele LightFM charge -- users=%d, items=%d",
        len(_user_id_map), len(_item_id_map),
    )
    return True


def is_model_available() -> bool:
    return _model is not None


def is_user_known(user_id: str) -> bool:
    return user_id in _user_id_map


def predict_scores(user_id: str, candidate_item_ids: list[str]) -> dict[str, float]:

    if _model is None:
        return {}

    if user_id not in _user_id_map:
        return {}

    user_idx = _user_id_map[user_id]

    known_items = []
    known_indices = []
    for iid in candidate_item_ids:
        if iid in _item_id_map:
            known_items.append(iid)
            known_indices.append(_item_id_map[iid])

    if not known_indices:
        return {}

    item_indices = np.array(known_indices, dtype=np.int32)

    scores = _model.predict(
        user_ids=user_idx,
        item_ids=item_indices,
        item_features=_item_features,
        user_features=_user_features,
    )

    return {iid: float(score) for iid, score in zip(known_items, scores)}


def reload_if_updated() -> bool:

    if not MODEL_PATH.exists():
        return False

    current_mtime = os.path.getmtime(MODEL_PATH)
    if current_mtime != _model_mtime:
        logger.info("Nouveau modele detecte, rechargement...")
        return load_model()

    return False