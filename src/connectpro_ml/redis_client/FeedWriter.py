#
# import logging
#
# from connectpro_ml.redis_client.RedisClient import get_redis
#
# logger = logging.getLogger(__name__)
#
# FEED_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 jours
#
#
# async def write_user_feed(user_id: str, scored_items: list) -> None:
#
#     r = get_redis()
#     key = f"feed:user:{user_id}"
#
#     async with r.pipeline(transaction=True) as pipe:
#
#         pipe.delete(key)
#
#         if scored_items:
#             mapping = {
#                 f"{item.item_type}:{item.item_id}": item.score
#                 for item in scored_items
#             }
#             pipe.zadd(key, mapping)
#             pipe.expire(key, FEED_TTL_SECONDS)
#
#         await pipe.execute()
#
#     logger.info(" Feed écrit dans Redis — user=%s, items=%d, key=%s", user_id, len(scored_items), key)
#
#
# async def read_user_feed(user_id: str, skip: int = 0, take: int = 20) -> list[dict]:
#
#     r = get_redis()
#     key = f"feed:user:{user_id}"
#
#     entries = await r.zrevrange(key, skip, skip + take - 1, withscores=True)
#
#     result = []
#     for member, score in entries:
#         parts = member.split(":", 1)
#         if len(parts) == 2:
#             result.append({
#                 "item_type": parts[0],
#                 "item_id": parts[1],
#                 "score": score,
#             })
#
#     return result
#
#
# async def delete_user_feed(user_id: str) -> None:
#
#     r = get_redis()
#     await r.delete(f"feed:user:{user_id}")

"""
Feed writer  écrit le feed précalculé dans Redis.


  feed:user:{userId}  → Sorted Set (member="{type}:{id}", score=float)
  TTL : 7 jours
"""
import logging

from connectpro_ml.redis_client.RedisClient import get_redis

logger = logging.getLogger(__name__)

FEED_TTL_SECONDS = 7 * 24 * 60 * 60  # temps ttl


async def write_user_feed(user_id: str, scored_items: list) -> None:
    r = get_redis()
    key = f"feed:user:{user_id}"

    async with r.pipeline(transaction=True) as pipe:
        pipe.delete(key)

        if scored_items:
            mapping = {
                f"{item.item_type}:{item.item_id}": float(item.score)
                for item in scored_items
            }
            pipe.zadd(key, mapping)
            pipe.expire(key, FEED_TTL_SECONDS)

        await pipe.execute()

    logger.info(" Feed écrit dans Redis — user=%s, items=%d, key=%s", user_id, len(scored_items), key)


async def read_user_feed(user_id: str, skip: int = 0, take: int = 20) -> list[dict]:
    r = get_redis()
    key = f"feed:user:{user_id}"

    entries = await r.zrevrange(key, skip, skip + take - 1, withscores=True)

    result = []
    for member, score in entries:
        parts = member.split(":", 1)
        if len(parts) == 2:
            result.append({
                "item_type": parts[0],
                "item_id": parts[1],
                "score": score,
            })

    return result


async def delete_user_feed(user_id: str) -> None:
    r = get_redis()
    await r.delete(f"feed:user:{user_id}")