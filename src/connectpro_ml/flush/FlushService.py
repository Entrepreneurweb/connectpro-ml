import logging
from datetime import datetime, timezone

import numpy as np
from asyncpg import Connection

from connectpro_ml.persistence.Database import get_connection
from connectpro_ml.embedding.EmbeddingService import EMBEDDING_VERSION

logger = logging.getLogger(__name__)


async def flush_user(user_id: str) -> None:
    """
    1. Lire le buffer pending_interactions
    2. Déplacer vers interactions (dédup)
    3. Mettre à jour les affinités (catégorie, tags, skills)
    4. Mettre à jour l'embedding long terme
    5. Vider le buffer
    6. Recalculer le feed
    """
    async with get_connection() as conn:
        async with conn.transaction():
            # 1. Lire le buffer
            pending = await conn.fetch(
                """
                SELECT id, user_id, item_type, item_id, interaction_type,
                       weight, source, position, occurred_at
                FROM pending_interactions
                WHERE user_id = $1
                ORDER BY occurred_at
                """,
                user_id,
            )

            if not pending:
                return

            logger.info(" Flush — user=%s, pending=%d interactions", user_id, len(pending))


            await _move_to_interactions(conn, pending)

            await _update_affinities(conn, user_id, pending)

            await _update_long_term_profile(conn, user_id, pending)

            pending_ids = [row["id"] for row in pending]
            await conn.execute(
                "DELETE FROM pending_interactions WHERE id = ANY($1)",
                pending_ids,
            )

        logger.info(" Flush terminé — user=%s", user_id)

    from connectpro_ml.scoring.ScoringWorker import enqueue_scoring
    enqueue_scoring(user_id, reason="flush")


async def _move_to_interactions(conn: Connection, pending: list) -> None:
     for row in pending:
        await conn.execute(
            """
            INSERT INTO interactions
                (user_id, item_type, item_id, interaction_type, weight, source, position, occurred_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id, item_id, interaction_type) DO UPDATE
                SET weight = EXCLUDED.weight,
                    occurred_at = GREATEST(interactions.occurred_at, EXCLUDED.occurred_at),
                    source = EXCLUDED.source,
                    position = EXCLUDED.position
            """,
            row["user_id"],
            row["item_type"],
            row["item_id"],
            row["interaction_type"],
            row["weight"],
            row["source"],
            row["position"],
            row["occurred_at"],
        )



async def _update_affinities(conn: Connection, user_id: str, pending: list) -> None:

    service_ids = list({
        row["item_id"] for row in pending if row["item_type"] == "service"
    })

    if not service_ids:
        return

    items_meta = await conn.fetch(
        """
        SELECT
            s.id as service_id,
            s.category_id,
            s.portfolio_id
        FROM services s
        WHERE s.id = ANY($1)
        """,
        service_ids,
    )
    items_map = {row["service_id"]: row for row in items_meta}

    # Tags par service
    tags_rows = await conn.fetch(
        "SELECT service_id, value FROM service_tags WHERE service_id = ANY($1)",
        service_ids,
    )
    tags_map: dict[str, list[str]] = {}
    for row in tags_rows:
        tags_map.setdefault(row["service_id"], []).append(row["value"])

    portfolio_ids = list({row["portfolio_id"] for row in items_meta if row["portfolio_id"]})
    skills_map: dict[str, list[str]] = {}
    if portfolio_ids:
        skills_rows = await conn.fetch(
            "SELECT portfolio_id, skill FROM portfolio_skills WHERE portfolio_id = ANY($1)",
            portfolio_ids,
        )
        for row in skills_rows:
            skills_map.setdefault(row["portfolio_id"], []).append(row["skill"])

    cat_scores: dict[str, float] = {}
    tag_scores: dict[str, float] = {}
    skill_scores: dict[str, float] = {}

    for interaction in pending:
        if interaction["item_type"] != "service":
            continue

        item = items_map.get(interaction["item_id"])
        if not item:
            continue

        weight = float(interaction["weight"])

        if item["category_id"]:
            cat_scores[item["category_id"]] = cat_scores.get(item["category_id"], 0) + weight

        for tag in tags_map.get(interaction["item_id"], []):
            tag_scores[tag] = tag_scores.get(tag, 0) + weight

        for skill in skills_map.get(item["portfolio_id"], []):
            skill_scores[skill] = skill_scores.get(skill, 0) + weight

    for cat_id, score in cat_scores.items():
        await conn.execute(
            """
            INSERT INTO user_category_affinity (user_id, category_id, score, interaction_count, last_updated)
            VALUES ($1, $2, $3, 1, NOW())
            ON CONFLICT (user_id, category_id) DO UPDATE
                SET score = user_category_affinity.score + EXCLUDED.score,
                    interaction_count = user_category_affinity.interaction_count + 1,
                    last_updated = NOW()
            """,
            user_id, cat_id, score,
        )

    # Upsert tags
    for tag, score in tag_scores.items():
        await conn.execute(
            """
            INSERT INTO user_tag_affinity (user_id, tag_value, score, interaction_count, last_updated)
            VALUES ($1, $2, $3, 1, NOW())
            ON CONFLICT (user_id, tag_value) DO UPDATE
                SET score = user_tag_affinity.score + EXCLUDED.score,
                    interaction_count = user_tag_affinity.interaction_count + 1,
                    last_updated = NOW()
            """,
            user_id, tag, score,
        )

    for skill, score in skill_scores.items():
        await conn.execute(
            """
            INSERT INTO user_skill_affinity (user_id, skill, score, interaction_count, last_updated)
            VALUES ($1, $2, $3, 1, NOW())
            ON CONFLICT (user_id, skill) DO UPDATE
                SET score = user_skill_affinity.score + EXCLUDED.score,
                    interaction_count = user_skill_affinity.interaction_count + 1,
                    last_updated = NOW()
            """,
            user_id, skill, score,
        )

    logger.info(
        "Affinités mises à jour — user=%s, cats=%d, tags=%d, skills=%d",
        user_id, len(cat_scores), len(tag_scores), len(skill_scores),
    )


async def _update_long_term_profile(conn: Connection, user_id: str, pending: list) -> None:

    item_ids = list({row["item_id"] for row in pending})

    embeddings_rows = await conn.fetch(
        """
        SELECT id, embedding FROM services WHERE id = ANY($1) AND embedding IS NOT NULL
        UNION ALL
        SELECT id, embedding FROM job_posts WHERE id = ANY($1) AND embedding IS NOT NULL
        """,
        item_ids,
    )
    embeddings_map = {row["id"]: row["embedding"] for row in embeddings_rows}

    new_vectors = []
    new_weights = []

    for interaction in pending:
        emb_bytes = embeddings_map.get(interaction["item_id"])
        if emb_bytes is None:
            continue

        vec = np.frombuffer(emb_bytes, dtype=np.float32)
        new_vectors.append(vec)
        new_weights.append(float(interaction["weight"]))

    if not new_vectors:
        logger.warning(" Aucun embedding trouvé pour les interactions — user=%s", user_id)
        return
    new_vectors_arr = np.array(new_vectors)
    new_weights_arr = np.array(new_weights)
    new_avg = np.average(new_vectors_arr, axis=0, weights=new_weights_arr)
    new_count = len(new_vectors)

    # Charger le profil existant
    existing = await conn.fetchrow(
        "SELECT semantic_embedding, total_interactions_used FROM user_profiles WHERE user_id = $1",
        user_id,
    )

    if existing and existing["semantic_embedding"]:
        old_profile = np.frombuffer(existing["semantic_embedding"], dtype=np.float32)
        old_count = existing["total_interactions_used"]

        total = old_count + new_count
        merged = (old_profile * old_count + new_avg * new_count) / total
    else:
        merged = new_avg
        total = new_count

    norm = np.linalg.norm(merged)
    if norm > 0:
        merged = merged / norm

    await conn.execute(
        """
        INSERT INTO user_profiles (user_id, semantic_embedding, total_interactions_used, embedding_version, last_computed_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            semantic_embedding = EXCLUDED.semantic_embedding,
            total_interactions_used = EXCLUDED.total_interactions_used,
            embedding_version = EXCLUDED.embedding_version,
            last_computed_at = NOW()
        """,
        user_id,
        merged.astype(np.float32).tobytes(),
        total,
        EMBEDDING_VERSION,
    )

    logger.info(
        " Profil embedding mis à jour — user=%s, total_interactions=%d",
        user_id, total,
    )