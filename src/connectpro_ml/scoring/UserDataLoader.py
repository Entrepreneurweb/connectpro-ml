"""
User data loader — charge toutes les données nécessaires d'un user
pour le scoring (requêtes séquentielles sur une seule connexion).
"""
import logging
from dataclasses import dataclass, field

import numpy as np
from asyncpg import Connection

logger = logging.getLogger(__name__)


@dataclass
class UserData:
    """Toutes les données d'un user nécessaires au scoring."""
    user_id: str
    long_term_embedding: np.ndarray | None = None
    total_interactions_used: int = 0
    cat_affinity: dict[str, float] = field(default_factory=dict)
    tag_affinity: dict[str, float] = field(default_factory=dict)
    skill_affinity: dict[str, float] = field(default_factory=dict)
    followed_portfolios: set[str] = field(default_factory=set)
    dismissed_items: set[str] = field(default_factory=set)
    recent_embeddings: list[tuple[np.ndarray, float]] = field(default_factory=list)

    @property
    def has_profile(self) -> bool:
        return self.long_term_embedding is not None or len(self.recent_embeddings) > 0


async def load_user_data(conn: Connection, user_id: str) -> UserData:
    """
    Charge toutes les données du user séquentiellement.
    Retourne un UserData prêt pour le scoring.
    """
    # Profil embedding long terme
    profile_row = await conn.fetchrow(
        "SELECT semantic_embedding, total_interactions_used FROM user_profiles WHERE user_id = $1",
        user_id,
    )

    # Affinités catégorie
    cat_rows = await conn.fetch(
        "SELECT category_id, score FROM user_category_affinity WHERE user_id = $1",
        user_id,
    )

    # Affinités tags
    tag_rows = await conn.fetch(
        "SELECT tag_value, score FROM user_tag_affinity WHERE user_id = $1",
        user_id,
    )

    # Affinités skills
    skill_rows = await conn.fetch(
        "SELECT skill, score FROM user_skill_affinity WHERE user_id = $1",
        user_id,
    )

    # Freelances suivis
    follow_rows = await conn.fetch(
        "SELECT portfolio_id FROM follows WHERE user_id = $1",
        user_id,
    )

    # Items rejetés
    dismissed_rows = await conn.fetch(
        "SELECT item_id FROM dismissed_items WHERE user_id = $1",
        user_id,
    )

    # Interactions récentes (pour le profil court terme)
    recent_rows = await conn.fetch(
        """
        SELECT s.embedding, i.weight, i.occurred_at
        FROM interactions i
        JOIN services s ON s.id = i.item_id
        WHERE i.user_id = $1
          AND s.embedding IS NOT NULL
          AND i.occurred_at > NOW() - INTERVAL '30 days'
        ORDER BY i.occurred_at DESC
        LIMIT 50
        """,
        user_id,
    )

    # Construire le UserData
    data = UserData(user_id=user_id)

    # Profil long terme
    if profile_row and profile_row["semantic_embedding"]:
        data.long_term_embedding = np.frombuffer(profile_row["semantic_embedding"], dtype=np.float32)
        data.total_interactions_used = profile_row["total_interactions_used"]

    # Affinités
    data.cat_affinity = {str(r["category_id"]): float(r["score"]) for r in cat_rows}
    data.tag_affinity = {r["tag_value"]: float(r["score"]) for r in tag_rows}
    data.skill_affinity = {r["skill"]: float(r["score"]) for r in skill_rows}

    # Follows et dismissed
    data.followed_portfolios = {str(r["portfolio_id"]) for r in follow_rows}
    data.dismissed_items = {str(r["item_id"]) for r in dismissed_rows}

    # Embeddings récents
    for row in recent_rows:
        vec = np.frombuffer(row["embedding"], dtype=np.float32)
        data.recent_embeddings.append((vec, float(row["weight"])))

    logger.info(
        "📋 User data loaded — user=%s, lt_profile=%s, cats=%d, tags=%d, skills=%d, follows=%d, recent=%d",
        user_id,
        data.long_term_embedding is not None,
        len(data.cat_affinity),
        len(data.tag_affinity),
        len(data.skill_affinity),
        len(data.followed_portfolios),
        len(data.recent_embeddings),
    )

    return data