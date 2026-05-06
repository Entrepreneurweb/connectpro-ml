"""
Feature builder  construit les matrices d'interactions et de features
necessaires a l'entrainement de LightFM depuis PostgreSQL.
"""
import logging
from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from lightfm import LightFM

from connectpro_ml.persistence.Database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class TrainingData:
    interactions: coo_matrix          # matrice user x item
    item_features: csr_matrix | None  # features des items
    user_features: csr_matrix | None  # features des users
    user_id_map: dict[str, int]       # uuid -> index interne
    item_id_map: dict[str, int]       # uuid -> index interne
    user_feature_names: list[str]     # noms des features user
    item_feature_names: list[str]     # noms des features item
    reverse_user_map: dict[int, str]  # index -> uuid
    reverse_item_map: dict[int, str]  # index -> uuid


async def build_training_data() -> TrainingData | None:

    async with get_connection() as conn:

        interaction_rows = await conn.fetch(
            """
            SELECT user_id, item_id, weight
            FROM interactions
            WHERE item_type = 'service'
            """
        )

        if not interaction_rows:
            logger.warning("Aucune interaction trouvee, entrainement impossible")
            return None

        user_ids = sorted({str(r["user_id"]) for r in interaction_rows})
        item_ids_from_interactions = {str(r["item_id"]) for r in interaction_rows}

        active_services = await conn.fetch(
            "SELECT id FROM services WHERE status = 'active' AND embedding IS NOT NULL"
        )
        all_item_ids = sorted(
            item_ids_from_interactions | {str(r["id"]) for r in active_services}
        )

        user_id_map = {uid: idx for idx, uid in enumerate(user_ids)}
        item_id_map = {iid: idx for idx, iid in enumerate(all_item_ids)}
        reverse_user_map = {idx: uid for uid, idx in user_id_map.items()}
        reverse_item_map = {idx: iid for iid, idx in item_id_map.items()}

        n_users = len(user_id_map)
        n_items = len(item_id_map)

        logger.info(
            "Construction des matrices -- users=%d, items=%d, interactions=%d",
            n_users, n_items, len(interaction_rows),
        )

        rows, cols, data = [], [], []
        for r in interaction_rows:
            uid = str(r["user_id"])
            iid = str(r["item_id"])
            if uid in user_id_map and iid in item_id_map:
                rows.append(user_id_map[uid])
                cols.append(item_id_map[iid])
                data.append(float(r["weight"]))

        interactions = coo_matrix(
            (np.array(data), (np.array(rows), np.array(cols))),
            shape=(n_users, n_items),
        )

        item_features, item_feature_names = await _build_item_features(
            conn, all_item_ids, item_id_map, n_items
        )

        user_features, user_feature_names = await _build_user_features(
            conn, user_ids, user_id_map, n_users
        )

    return TrainingData(
        interactions=interactions,
        item_features=item_features,
        user_features=user_features,
        user_id_map=user_id_map,
        item_id_map=item_id_map,
        user_feature_names=item_feature_names,
        item_feature_names=item_feature_names,
        reverse_user_map=reverse_user_map,
        reverse_item_map=reverse_item_map,
    )


async def _build_item_features(
    conn, item_ids: list[str], item_id_map: dict[str, int], n_items: int
) -> tuple[csr_matrix | None, list[str]]:


    tag_rows = await conn.fetch(
        "SELECT service_id, value FROM service_tags WHERE service_id = ANY($1)",
        [iid for iid in item_ids if iid in item_id_map],
    )


    cat_rows = await conn.fetch(
        """
        SELECT s.id as service_id, c.value as category_name
        FROM services s
        JOIN categories c ON c.id = s.category_id
        WHERE s.id = ANY($1)
        """,
        [iid for iid in item_ids if iid in item_id_map],
    )


    award_rows = await conn.fetch(
        "SELECT service_id, value FROM service_awards WHERE service_id = ANY($1)",
        [iid for iid in item_ids if iid in item_id_map],
    )

    all_features = set()
    for r in tag_rows:
        all_features.add(f"tag:{r['value']}")
    for r in cat_rows:
        all_features.add(f"cat:{r['category_name']}")
    for r in award_rows:
        all_features.add(f"award:{r['value']}")

    if not all_features:
        return None, []

    feature_names = sorted(all_features)
    feature_map = {f: idx for idx, f in enumerate(feature_names)}
    n_features = len(feature_names)

    total_cols = n_items + n_features
    rows, cols, data = [], [], []


    for idx in range(n_items):
        rows.append(idx)
        cols.append(idx)
        data.append(1.0)


    for r in tag_rows:
        iid = str(r["service_id"])
        if iid in item_id_map:
            feat = f"tag:{r['value']}"
            rows.append(item_id_map[iid])
            cols.append(n_items + feature_map[feat])
            data.append(1.0)


    for r in cat_rows:
        iid = str(r["service_id"])
        if iid in item_id_map:
            feat = f"cat:{r['category_name']}"
            rows.append(item_id_map[iid])
            cols.append(n_items + feature_map[feat])
            data.append(1.0)


    for r in award_rows:
        iid = str(r["service_id"])
        if iid in item_id_map:
            feat = f"award:{r['value']}"
            rows.append(item_id_map[iid])
            cols.append(n_items + feature_map[feat])
            data.append(1.0)

    matrix = csr_matrix(
        (np.array(data), (np.array(rows), np.array(cols))),
        shape=(n_items, total_cols),
    )

    logger.info("Item features construites -- features=%d", n_features)
    return matrix, feature_names


async def _build_user_features(
    conn, user_ids: list[str], user_id_map: dict[str, int], n_users: int
) -> tuple[csr_matrix | None, list[str]]:


    cat_rows = await conn.fetch(
        """
        SELECT uca.user_id, c.value as category_name, uca.score
        FROM user_category_affinity uca
        JOIN categories c ON c.id = uca.category_id
        WHERE uca.user_id = ANY($1)
        """,
        [uid for uid in user_ids if uid in user_id_map],
    )


    tag_rows = await conn.fetch(
        """
        SELECT user_id, tag_value, score
        FROM user_tag_affinity
        WHERE user_id = ANY($1)
        """,
        [uid for uid in user_ids if uid in user_id_map],
    )


    all_features = set()
    for r in cat_rows:
        all_features.add(f"pref_cat:{r['category_name']}")
    for r in tag_rows:
        all_features.add(f"pref_tag:{r['tag_value']}")

    if not all_features:
        return None, []

    feature_names = sorted(all_features)
    feature_map = {f: idx for idx, f in enumerate(feature_names)}
    n_features = len(feature_names)

    total_cols = n_users + n_features
    rows, cols, data = [], [], []


    for idx in range(n_users):
        rows.append(idx)
        cols.append(idx)
        data.append(1.0)


    for r in cat_rows:
        uid = str(r["user_id"])
        if uid in user_id_map:
            feat = f"pref_cat:{r['category_name']}"
            rows.append(user_id_map[uid])
            cols.append(n_users + feature_map[feat])
            data.append(float(r["score"]))


    for r in tag_rows:
        uid = str(r["user_id"])
        if uid in user_id_map:
            feat = f"pref_tag:{r['tag_value']}"
            rows.append(user_id_map[uid])
            cols.append(n_users + feature_map[feat])
            data.append(float(r["score"]))

    matrix = csr_matrix(
        (np.array(data), (np.array(rows), np.array(cols))),
        shape=(n_users, total_cols),
    )

    logger.info("User features construites -- features=%d", n_features)
    return matrix, feature_names