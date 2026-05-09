"""
Cache layer — in-memory (default) or Redis (if REDIS_URL set).
"""

import asyncio
import json
import os
import time
from typing import Any


class Cache:
    """
    Thin async cache. Uses Redis if REDIS_URL is set, otherwise in-process dict.
    All values are JSON-serialised.
    """

    def __init__(self):
        self._redis = None
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expiry_ts)
        self._redis_url = os.getenv("REDIS_URL", "")

    async def connect(self):
        if self._redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
                print(f"[cache] Connected to Redis at {self._redis_url}")
            except Exception as e:
                print(f"[cache] Redis unavailable ({e}), using in-memory cache")
                self._redis = None
        else:
            print("[cache] Using in-memory cache (set REDIS_URL for Redis)")

    async def get(self, key: str) -> Any | None:
        if self._redis:
            try:
                val = await self._redis.get(key)
                return json.loads(val) if val else None
            except Exception:
                return None

        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry < time.time():
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int = 300):
        if self._redis:
            try:
                await self._redis.setex(key, ttl, json.dumps(value, default=str))
            except Exception:
                pass
            return

        self._store[key] = (value, time.time() + ttl)

    async def delete(self, key: str):
        if self._redis:
            await self._redis.delete(key)
        else:
            self._store.pop(key, None)

    async def close(self):
        if self._redis:
            await self._redis.aclose()
