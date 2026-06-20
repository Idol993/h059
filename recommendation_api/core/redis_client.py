import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
from .config import settings


class RedisClient:
    _instance: Optional["RedisClient"] = None
    _client: Optional[redis.Redis] = None

    def __new__(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self) -> None:
        if self._client is None:
            self._client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
            )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def is_connected(self) -> bool:
        try:
            if self._client:
                await self._client.ping()
                return True
            return False
        except Exception:
            return False

    async def get(self, key: str) -> Optional[str]:
        if not self._client:
            return None
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        if not self._client:
            return
        if ttl:
            await self._client.setex(key, ttl, value)
        else:
            await self._client.set(key, value)

    async def get_json(self, key: str) -> Optional[Any]:
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        await self.set(key, json.dumps(value, ensure_ascii=False), ttl)

    async def delete(self, key: str) -> None:
        if self._client:
            await self._client.delete(key)

    async def hgetall(self, key: str) -> Dict[str, str]:
        if not self._client:
            return {}
        return await self._client.hgetall(key)

    async def hset(self, key: str, mapping: Dict[str, str]) -> None:
        if not self._client:
            return
        await self._client.hset(key, mapping=mapping)

    async def incr(self, key: str) -> int:
        if not self._client:
            return 0
        return await self._client.incr(key)

    async def sadd(self, key: str, *values: str) -> int:
        if not self._client:
            return 0
        return await self._client.sadd(key, *values)

    async def smembers(self, key: str) -> set:
        if not self._client:
            return set()
        return await self._client.smembers(key)

    async def exists(self, key: str) -> bool:
        if not self._client:
            return False
        return await self._client.exists(key) > 0


redis_client = RedisClient()


async def get_redis_client() -> RedisClient:
    await redis_client.init()
    return redis_client
