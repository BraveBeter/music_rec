"""Redis client utility."""
import redis.asyncio as aioredis
from common.config import get_settings

settings = get_settings()

redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the Redis client singleton."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis():
    """Close the Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
