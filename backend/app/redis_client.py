from redis.asyncio import Redis

from app.config import Settings


def create_redis(settings: Settings) -> Redis:
    """Create an async Redis client."""
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
