
import logging
from datetime import datetime, timezone

from asyncpg import Connection

logger = logging.getLogger(__name__)


def parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def insert_pending_interaction(conn: Connection, data: dict) -> None:

    await conn.execute(
        """
        INSERT INTO pending_interactions 
            (user_id, item_type, item_id, interaction_type, weight, source, position, occurred_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        data["user_id"],
        data.get("item_type", "service"),
        data["item_id"],
        data["interaction_type"],
        data.get("weight", 1.0),
        data.get("source"),
        data.get("position"),
        parse_timestamp(data.get("timestamp")),
    )
    logger.info(
        "Pending interaction saved — user=%s, type=%s, item=%s",
        data["user_id"], data["interaction_type"], data["item_id"],
    )


async def insert_follow(conn: Connection, data: dict) -> None:

    await conn.execute(
        """
        INSERT INTO follows (user_id, portfolio_id, created_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, portfolio_id) DO NOTHING
        """,
        data["user_id"],
        data["portfolio_id"],
        parse_timestamp(data.get("timestamp")),
    )
    logger.info(
        " Follow saved — user=%s, portfolio=%s",
        data["user_id"], data["portfolio_id"],
    )


async def delete_follow(conn: Connection, data: dict) -> None:
    await conn.execute(
        "DELETE FROM follows WHERE user_id = $1 AND portfolio_id = $2",
        data["user_id"],
        data["portfolio_id"],
    )
    logger.info(
        " Unfollow — user=%s, portfolio=%s",
        data["user_id"], data["portfolio_id"],
    )


async def insert_dismissed_item(conn: Connection, data: dict) -> None:

    await conn.execute(
        """
        INSERT INTO dismissed_items (user_id, item_id, item_type, dismissed_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, item_id) DO NOTHING
        """,
        data["user_id"],
        data["item_id"],
        data.get("item_type", "service"),
        parse_timestamp(data.get("timestamp")),
    )
    logger.info(
        " Item dismissed — user=%s, item=%s",
        data["user_id"], data["item_id"],
    )