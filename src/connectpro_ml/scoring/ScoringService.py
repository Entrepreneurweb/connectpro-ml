
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from asyncpg import Connection

from connectpro_ml.persistence.Database import get_connection
from connectpro_ml.scoring.UserDataLoader import load_user_data, UserData
from connectpro_ml.model.ModelLoader import is_model_available, is_user_known, predict_scores

logger = logging.getLogger(__name__)

TOP_N = 200
LONG_TERM_WEIGHT = 0.6
SHORT_TERM_WEIGHT = 0.4


@dataclass
class ScoredItem:
    item_id: str
    item_type: str
    score: float


# determiner le poids de content based vs collaborative based

def _compute_alpha(total_interactions: int) -> float:

    if total_interactions < 5:
        return 0.0
    elif total_interactions < 20:
        return 0.3
    elif total_interactions < 50:
        return 0.6
    else:
        return 0.8




async def compute_feed(user_id: str) -> list[ScoredItem]:

    start = time.monotonic()

    async with get_connection() as conn:
        user_data = await load_user_data(conn, user_id)

        if not user_data.has_profile:
            logger.info("Cold start -- user=%s, aucun profil ni interaction", user_id)
            return await _cold_start_feed(conn)

        user_vector = _build_user_vector(user_data)
        candidates = await _fetch_candidates(conn, user_data)

        if not candidates:
            logger.warning("Aucun candidat trouve -- user=%s", user_id)
            return []

        # scoring strategy
        use_lightfm = is_model_available() and is_user_known(user_id)
        alpha = _compute_alpha(user_data.total_interactions_used) if use_lightfm else 0.0

        #  light fm score
        lf_scores = {}
        if use_lightfm and alpha > 0:
            candidate_ids = [c.item_id for c in candidates]
            lf_scores = predict_scores(user_id, candidate_ids)

        # Scorer chaque candidat
        scored = _score_candidates(user_vector, user_data, candidates, lf_scores, alpha)

        scored.sort(key=lambda x: x.score, reverse=True)
        result = scored[:TOP_N]

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Feed calcule -- user=%s, candidats=%d, top=%d, alpha=%.1f, lightfm=%s, duration=%dms",
            user_id, len(candidates), len(result), alpha, use_lightfm, duration_ms,
        )

        return result




def _build_user_vector(user_data: UserData) -> np.ndarray | None:
    long_term = user_data.long_term_embedding
    short_term = _compute_short_term(user_data.recent_embeddings)

    if long_term is not None and short_term is not None:
        combined = LONG_TERM_WEIGHT * long_term + SHORT_TERM_WEIGHT * short_term
    elif long_term is not None:
        combined = long_term
    elif short_term is not None:
        combined = short_term
    else:
        return None

    norm = np.linalg.norm(combined)
    if norm > 0:
        combined = combined / norm
    return combined


def _compute_short_term(recent_embeddings: list[tuple[np.ndarray, float]]) -> np.ndarray | None:
    if not recent_embeddings:
        return None

    vectors = np.array([vec for vec, _ in recent_embeddings])
    weights = np.array([w for _, w in recent_embeddings])
    avg = np.average(vectors, axis=0, weights=weights)

    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg


@dataclass
class Candidate:
    item_id: str
    item_type: str
    embedding: np.ndarray
    category_id: str | None
    portfolio_id: str | None
    tags: list[str]
    created_at: datetime | None
    avg_rating: float | None
    review_count: int


async def _fetch_candidates(conn: Connection, user_data: UserData) -> list[Candidate]:
    rows = await conn.fetch(
        """
        SELECT
            s.id, s.embedding, s.category_id, s.portfolio_id, s.created_at,
            COALESCE(rs.avg_rating, 0) as avg_rating,
            COALESCE(rs.review_count, 0) as review_count
        FROM services s
        LEFT JOIN service_review_stats rs ON rs.service_id = s.id
        WHERE s.status = 'active' AND s.embedding IS NOT NULL
        """,
    )

    service_ids = [row["id"] for row in rows]
    tag_rows = await conn.fetch(
        "SELECT service_id, value FROM service_tags WHERE service_id = ANY($1)",
        service_ids,
    )
    tags_map: dict[str, list[str]] = {}
    for tr in tag_rows:
        tags_map.setdefault(str(tr["service_id"]), []).append(tr["value"])

    candidates = []
    for row in rows:
        item_id = str(row["id"])
        if item_id in user_data.dismissed_items:
            continue

        candidates.append(Candidate(
            item_id=item_id,
            item_type="service",
            embedding=np.frombuffer(row["embedding"], dtype=np.float32),
            category_id=str(row["category_id"]) if row["category_id"] else None,
            portfolio_id=str(row["portfolio_id"]) if row["portfolio_id"] else None,
            tags=tags_map.get(item_id, []),
            created_at=row["created_at"],
            avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
            review_count=int(row["review_count"]),
        ))

    return candidates


# hybrid scoring

def _score_candidates(
    user_vector: np.ndarray | None,
    user_data: UserData,
    candidates: list[Candidate],
    lf_scores: dict[str, float],
    alpha: float,
) -> list[ScoredItem]:
    now = datetime.now(timezone.utc)

    # Score content-based vectorise
    if user_vector is not None:
        embeddings_matrix = np.array([c.embedding for c in candidates])
        cosine_scores = embeddings_matrix @ user_vector
    else:
        cosine_scores = np.zeros(len(candidates))

    # Normalisation des scores LightFM entre 0 et 1 (si disponibles)
    lf_values = list(lf_scores.values()) if lf_scores else []
    if lf_values:
        lf_min = min(lf_values)
        lf_max = max(lf_values)
        lf_range = lf_max - lf_min if lf_max != lf_min else 1.0
    else:
        lf_min, lf_range = 0.0, 1.0

    scored = []
    for i, candidate in enumerate(candidates):
        #  Score content-based avec boosts
        cb_score = float(cosine_scores[i])
        if cb_score < 0.05 and candidate.item_id not in lf_scores:
            continue

        # Boost categorie
        cat_boost = 1.0
        if candidate.category_id and candidate.category_id in user_data.cat_affinity:
            affinity = user_data.cat_affinity[candidate.category_id]
            cat_boost = 1 + np.log1p(affinity) / 5

        # Boost tags
        tag_score = sum(user_data.tag_affinity.get(tag, 0) for tag in candidate.tags)
        tag_boost = 1 + np.log1p(tag_score) / 8

        # Boost qualite
        if candidate.review_count > 0 and candidate.avg_rating:
            quality_boost = 0.7 + (
                (candidate.avg_rating / 5)
                * np.sqrt(min(candidate.review_count, 100) / 100)
                * 0.6
            )
        else:
            quality_boost = 0.85

        # Boost fraicheur
        freshness_boost = 1.0
        if candidate.created_at:
            age_days = max((now - candidate.created_at.replace(tzinfo=timezone.utc)).days, 0)
            freshness_boost = 0.8 + np.exp(-age_days / 90) * 0.4

        # Boost follow
        follow_boost = 1.0
        if candidate.portfolio_id and candidate.portfolio_id in user_data.followed_portfolios:
            follow_boost = 2.0

        cb_final = cb_score * cat_boost * tag_boost * quality_boost * freshness_boost * follow_boost

        #  Score LightFM (normalise entre 0 et 1)
        lf_final = 0.0
        if candidate.item_id in lf_scores:
            lf_raw = lf_scores[candidate.item_id]
            lf_final = (lf_raw - lf_min) / lf_range

        #  Blending
        final_score = alpha * lf_final + (1 - alpha) * cb_final

        scored.append(ScoredItem(
            item_id=candidate.item_id,
            item_type=candidate.item_type,
            score=final_score,
        ))

    return scored

# cold start
async def _cold_start_feed(conn: Connection) -> list[ScoredItem]:
    rows = await conn.fetch(
        """
        SELECT s.id,
            COALESCE(rs.avg_rating, 0) as avg_rating,
            COALESCE(rs.review_count, 0) as review_count
        FROM services s
        LEFT JOIN service_review_stats rs ON rs.service_id = s.id
        WHERE s.status = 'active' AND s.embedding IS NOT NULL
        ORDER BY
            COALESCE(rs.avg_rating, 0) * LN(COALESCE(rs.review_count, 0) + 1) DESC,
            s.created_at DESC
        LIMIT $1
        """,
        TOP_N,
    )

    scored = []
    for rank, row in enumerate(rows):
        score = 1.0 / (rank + 1)
        scored.append(ScoredItem(
            item_id=str(row["id"]),
            item_type="service",
            score=score,
        ))

    logger.info("Cold start feed genere -- %d items", len(scored))
    return scored
#
# import logging
# import time
# from dataclasses import dataclass
# from datetime import datetime, timezone
#
# import numpy as np
# from asyncpg import Connection
#
# from connectpro_ml.persistence.Database import get_connection
# from connectpro_ml.scoring.UserDataLoader import load_user_data, UserData
#
# logger = logging.getLogger(__name__)
#
#
# TOP_N = 200
# LONG_TERM_WEIGHT = 0.6
# SHORT_TERM_WEIGHT = 0.4
#
#
# @dataclass
# class ScoredItem:
#     item_id: str
#     item_type: str  # 'service' | 'job_post'
#     score: float
#
#
# async def compute_feed(user_id: str) -> list[ScoredItem]:
#
#     start = time.monotonic()
#
#     async with get_connection() as conn:
#
#         user_data = await load_user_data(conn, user_id)
#
#         if not user_data.has_profile:
#             logger.info(" Cold start — user=%s, aucun profil ni interaction", user_id)
#             return await _cold_start_feed(conn)
#
#         user_vector = _build_user_vector(user_data)
#
#         if user_vector is None:
#             logger.warning(" Impossible de construire un vecteur user — user=%s", user_id)
#             return await _cold_start_feed(conn)
#
#         candidates = await _fetch_candidates(conn, user_data)
#
#         if not candidates:
#             logger.warning(" Aucun candidat trouvé — user=%s", user_id)
#             return []
#
#         scored = _score_candidates(user_vector, user_data, candidates)
#
#         scored.sort(key=lambda x: x.score, reverse=True)
#         result = scored[:TOP_N]
#
#         duration_ms = int((time.monotonic() - start) * 1000)
#         logger.info(
#             " Feed calculé — user=%s, candidats=%d, top=%d, duration=%dms",
#             user_id, len(candidates), len(result), duration_ms,
#         )
#
#         return result
#
#
# def _build_user_vector(user_data: UserData) -> np.ndarray | None:
#
#     long_term = user_data.long_term_embedding
#     short_term = _compute_short_term(user_data.recent_embeddings)
#
#     if long_term is not None and short_term is not None:
#         combined = LONG_TERM_WEIGHT * long_term + SHORT_TERM_WEIGHT * short_term
#     elif long_term is not None:
#         combined = long_term
#     elif short_term is not None:
#         combined = short_term
#     else:
#         return None
#
#     norm = np.linalg.norm(combined)
#     if norm > 0:
#         combined = combined / norm
#
#     return combined
#
#
# def _compute_short_term(recent_embeddings: list[tuple[np.ndarray, float]]) -> np.ndarray | None:
#
#     if not recent_embeddings:
#         return None
#
#     vectors = np.array([vec for vec, _ in recent_embeddings])
#     weights = np.array([w for _, w in recent_embeddings])
#
#     avg = np.average(vectors, axis=0, weights=weights)
#     norm = np.linalg.norm(avg)
#     if norm > 0:
#         avg = avg / norm
#
#     return avg
#
#
# @dataclass
# class Candidate:
#     item_id: str
#     item_type: str
#     embedding: np.ndarray
#     category_id: str | None
#     portfolio_id: str | None
#     tags: list[str]
#     created_at: datetime | None
#     avg_rating: float | None
#     review_count: int
#
#
# async def _fetch_candidates(conn: Connection, user_data: UserData) -> list[Candidate]:
#
#     rows = await conn.fetch(
#         """
#         SELECT
#             s.id,
#             s.embedding,
#             s.category_id,
#             s.portfolio_id,
#             s.created_at,
#             COALESCE(rs.avg_rating, 0) as avg_rating,
#             COALESCE(rs.review_count, 0) as review_count
#         FROM services s
#         LEFT JOIN service_review_stats rs ON rs.service_id = s.id
#         WHERE s.status = 'active'
#           AND s.embedding IS NOT NULL
#         """,
#     )
#
#     service_ids = [row["id"] for row in rows]
#     tag_rows = await conn.fetch(
#         "SELECT service_id, value FROM service_tags WHERE service_id = ANY($1)",
#         service_ids,
#     )
#     tags_map: dict[str, list[str]] = {}
#     for tr in tag_rows:
#         tags_map.setdefault(str(tr["service_id"]), []).append(tr["value"])
#
#     candidates = []
#     for row in rows:
#         item_id = str(row["id"])
#
#         if item_id in user_data.dismissed_items:
#             continue
#
#         candidates.append(Candidate(
#             item_id=item_id,
#             item_type="service",
#             embedding=np.frombuffer(row["embedding"], dtype=np.float32),
#             category_id=str(row["category_id"]) if row["category_id"] else None,
#             portfolio_id=str(row["portfolio_id"]) if row["portfolio_id"] else None,
#             tags=tags_map.get(item_id, []),
#             created_at=row["created_at"],
#             avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
#             review_count=int(row["review_count"]),
#         ))
#
#     return candidates
#
#
# def _score_candidates(
#     user_vector: np.ndarray,
#     user_data: UserData,
#     candidates: list[Candidate],
# ) -> list[ScoredItem]:
#
#     now = datetime.now(timezone.utc)
#
#     embeddings_matrix = np.array([c.embedding for c in candidates])
#     cosine_scores = embeddings_matrix @ user_vector
#
#     scored = []
#     for i, candidate in enumerate(candidates):
#         semantic = float(cosine_scores[i])
#
#         if semantic < 0.05:
#             continue
#
#         cat_boost = 1.0
#         if candidate.category_id and candidate.category_id in user_data.cat_affinity:
#             affinity = user_data.cat_affinity[candidate.category_id]
#             cat_boost = 1 + np.log1p(affinity) / 5
#
#         tag_score = 0.0
#         for tag in candidate.tags:
#             tag_score += user_data.tag_affinity.get(tag, 0)
#         tag_boost = 1 + np.log1p(tag_score) / 8
#
#         quality_boost = 1.0
#         if candidate.review_count > 0 and candidate.avg_rating:
#             quality_boost = 0.7 + (
#                 (candidate.avg_rating / 5)
#                 * np.sqrt(min(candidate.review_count, 100) / 100)
#                 * 0.6
#             )
#         else:
#             quality_boost = 0.85
#
#         freshness_boost = 1.0
#         if candidate.created_at:
#             age_days = max((now - candidate.created_at.replace(tzinfo=timezone.utc)).days, 0)
#             freshness_boost = 0.8 + np.exp(-age_days / 90) * 0.4
#
#         follow_boost = 1.0
#         if candidate.portfolio_id and candidate.portfolio_id in user_data.followed_portfolios:
#             follow_boost = 2.0
#
#         final_score = (
#             semantic
#             * cat_boost
#             * tag_boost
#             * quality_boost
#             * freshness_boost
#             * follow_boost
#         )
#
#         scored.append(ScoredItem(
#             item_id=candidate.item_id,
#             item_type=candidate.item_type,
#             score=final_score,
#         ))
#
#     return scored
#
#
# async def _cold_start_feed(conn: Connection) -> list[ScoredItem]:
#
#     rows = await conn.fetch(
#         """
#         SELECT
#             s.id,
#             COALESCE(rs.avg_rating, 0) as avg_rating,
#             COALESCE(rs.review_count, 0) as review_count,
#             s.created_at
#         FROM services s
#         LEFT JOIN service_review_stats rs ON rs.service_id = s.id
#         WHERE s.status = 'active'
#           AND s.embedding IS NOT NULL
#         ORDER BY
#             COALESCE(rs.avg_rating, 0) * LN(COALESCE(rs.review_count, 0) + 1) DESC,
#             s.created_at DESC
#         LIMIT $1
#         """,
#         TOP_N,
#     )
#
#     scored = []
#     for rank, row in enumerate(rows):
#
#         score = 1.0 / (rank + 1)
#         scored.append(ScoredItem(
#             item_id=str(row["id"]),
#             item_type="service",
#             score=score,
#         ))
#
#     logger.info(" Cold start feed généré — %d items", len(scored))
#     return scored