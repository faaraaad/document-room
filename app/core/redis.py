from typing import AsyncGenerator
import redis.asyncio as aioredis
from app.config import settings

# Async Redis connection pool setup
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=50,
    decode_responses=True
)

redis_client: aioredis.Redis = aioredis.Redis(connection_pool=redis_pool)


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    Dependency yielding an active Redis client from the shared connection pool.
    """
    client = aioredis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.close()
