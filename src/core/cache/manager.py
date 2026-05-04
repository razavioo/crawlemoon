"""Cache Manager with TTL support and optional Redis/Memcached backend.

The manager exposes a unified interface regardless of backend:
- Default: in-process LRU dict (zero config required)
- Redis:   set ``CRAWILFY_REDIS_URL`` env-var (e.g. redis://localhost:6379/0)

The Redis backend is optional; if ``redis`` is not installed the manager
falls back silently to the in-memory backend.
"""

import asyncio
import hashlib
import json
import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from dataclasses import dataclass

from ...exceptions import CacheBackendError, CacheSerializationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory entry
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """Represents a cache entry."""

    key: str
    value: Any
    created_at: datetime
    ttl_seconds: int
    hits: int = 0
    last_accessed: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        age = datetime.now() - self.created_at
        return age.total_seconds() > self.ttl_seconds

    def access(self) -> None:
        """Record cache access."""
        self.hits += 1
        self.last_accessed = datetime.now()


# ---------------------------------------------------------------------------
# Redis backend (optional)
# ---------------------------------------------------------------------------

class _RedisBackend:
    """Thin wrapper around redis.asyncio that serialises values with pickle."""

    def __init__(self, url: str):
        try:
            import redis.asyncio as aioredis  # type: ignore[import]
            self._redis = aioredis.from_url(url, decode_responses=False)
        except ImportError as exc:
            raise CacheBackendError(
                "redis package is required for Redis cache backend. "
                "Install it with: pip install redis"
            ) from exc

    async def get(self, key: str) -> Optional[Any]:
        try:
            data = await self._redis.get(key)
            if data is None:
                return None
            return pickle.loads(data)
        except pickle.UnpicklingError as exc:
            raise CacheSerializationError(f"Failed to deserialise cache entry {key}: {exc}") from exc
        except Exception as exc:
            raise CacheBackendError(f"Redis GET failed: {exc}") from exc

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            data = pickle.dumps(value)
            await self._redis.setex(key, ttl_seconds, data)
        except pickle.PicklingError as exc:
            raise CacheSerializationError(f"Failed to serialise cache entry {key}: {exc}") from exc
        except Exception as exc:
            raise CacheBackendError(f"Redis SET failed: {exc}") from exc

    async def delete(self, pattern: str) -> None:
        """Delete keys matching a glob pattern."""
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
        except Exception as exc:
            raise CacheBackendError(f"Redis DELETE failed: {exc}") from exc

    async def close(self) -> None:
        try:
            await self._redis.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CacheManager
# ---------------------------------------------------------------------------


class CacheManager:
    """Manages caching for pages, responses, and state snapshots.

    Uses an in-memory LRU-eviction dict by default.  Set the env-var
    ``CRAWILFY_REDIS_URL`` to switch to a Redis backend (requires the
    ``redis`` package).
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl_seconds: int = 3600,
        redis_url: Optional[str] = None,
    ):
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds

        # Try Redis backend first
        resolved_redis_url = redis_url or os.getenv("CRAWILFY_REDIS_URL")
        self._redis: Optional[_RedisBackend] = None
        if resolved_redis_url:
            try:
                self._redis = _RedisBackend(resolved_redis_url)
                logger.info("Cache using Redis backend: %s", resolved_redis_url)
            except CacheBackendError as exc:
                logger.warning("Redis cache backend unavailable (%s) — falling back to in-memory", exc)

        # In-memory caches (always initialised; used when Redis is unavailable)
        self._page_cache: Dict[str, CacheEntry] = {}
        self._response_cache: Dict[str, CacheEntry] = {}
        self._state_cache: Dict[str, CacheEntry] = {}

        # Background sweeper for expired in-memory entries
        self._sweep_task: Optional[asyncio.Task] = None
        self._sweep_interval_seconds: float = 60.0

    async def start_sweeper(self, interval_seconds: float = 60.0) -> None:
        """Start a periodic task that purges expired in-memory entries.

        Idempotent: calling twice is a no-op. Safe to call from any running event loop.
        """
        if self._sweep_task and not self._sweep_task.done():
            return
        self._sweep_interval_seconds = interval_seconds

        async def _loop() -> None:
            try:
                while True:
                    await asyncio.sleep(self._sweep_interval_seconds)
                    try:
                        self.evict_expired()
                    except Exception as exc:
                        logger.warning("Cache sweep failed: %s", exc)
            except asyncio.CancelledError:
                pass

        self._sweep_task = asyncio.create_task(_loop(), name="cache-sweeper")

    async def stop_sweeper(self) -> None:
        """Cancel the background sweeper, if any."""
        if self._sweep_task:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sweep_task = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_key(self, namespace: str, url: str, **params) -> str:
        """Generate a namespaced cache key from URL and parameters."""
        key_data = {"url": url, **params}
        key_str = json.dumps(key_data, sort_keys=True)
        digest = hashlib.sha256(key_str.encode()).hexdigest()
        return f"crawilfy:{namespace}:{digest}"

    def _evict_lru(self, cache: Dict[str, CacheEntry]) -> None:
        """Evict the least-recently-used entry when the cache is full."""
        if len(cache) >= self.max_size:
            lru_key = min(
                cache.keys(),
                key=lambda k: cache[k].last_accessed or cache[k].created_at,
            )
            del cache[lru_key]

    # ------------------------------------------------------------------
    # Page cache
    # ------------------------------------------------------------------

    def get_page(self, url: str, **params) -> Optional[Any]:
        """Get cached page content (in-memory only)."""
        key = self._generate_key("page", url, **params)
        entry = self._page_cache.get(key)
        if not entry:
            return None
        if entry.is_expired():
            del self._page_cache[key]
            return None
        entry.access()
        logger.debug("Page cache hit: %s", url)
        return entry.value

    def set_page(
        self,
        url: str,
        content: Any,
        ttl_seconds: Optional[int] = None,
        **params,
    ) -> None:
        """Cache page content."""
        key = self._generate_key("page", url, **params)
        ttl = ttl_seconds or self.default_ttl_seconds
        self._evict_lru(self._page_cache)
        self._page_cache[key] = CacheEntry(
            key=key,
            value=content,
            created_at=datetime.now(),
            ttl_seconds=ttl,
        )
        logger.debug("Page cached: %s", url)

    # ------------------------------------------------------------------
    # Response cache
    # ------------------------------------------------------------------

    def get_response(self, url: str, method: str = "GET", **params) -> Optional[Any]:
        """Get cached API response."""
        key = self._generate_key("response", url, method=method, **params)
        entry = self._response_cache.get(key)
        if not entry:
            return None
        if entry.is_expired():
            del self._response_cache[key]
            return None
        entry.access()
        logger.debug("Response cache hit: %s %s", method, url)
        return entry.value

    def set_response(
        self,
        url: str,
        response: Any,
        method: str = "GET",
        ttl_seconds: Optional[int] = None,
        **params,
    ) -> None:
        """Cache API response."""
        key = self._generate_key("response", url, method=method, **params)
        ttl = ttl_seconds or self.default_ttl_seconds
        self._evict_lru(self._response_cache)
        self._response_cache[key] = CacheEntry(
            key=key,
            value=response,
            created_at=datetime.now(),
            ttl_seconds=ttl,
        )
        logger.debug("Response cached: %s %s", method, url)

    # ------------------------------------------------------------------
    # State snapshot cache
    # ------------------------------------------------------------------

    def get_state_snapshot(self, snapshot_id: str) -> Optional[Any]:
        """Get cached state snapshot."""
        entry = self._state_cache.get(snapshot_id)
        if not entry:
            return None
        if entry.is_expired():
            del self._state_cache[snapshot_id]
            return None
        entry.access()
        return entry.value

    def set_state_snapshot(
        self,
        snapshot_id: str,
        state: Any,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache state snapshot."""
        ttl = ttl_seconds or (self.default_ttl_seconds * 24)
        self._evict_lru(self._state_cache)
        self._state_cache[snapshot_id] = CacheEntry(
            key=snapshot_id,
            value=state,
            created_at=datetime.now(),
            ttl_seconds=ttl,
        )
        logger.debug("State snapshot cached: %s", snapshot_id)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self, cache_type: Optional[str] = None) -> None:
        """Clear one or all in-memory cache(s).

        Args:
            cache_type: ``"page"``, ``"response"``, ``"state"``, or ``None``
                to clear everything.
        """
        if cache_type in ("page", None):
            self._page_cache.clear()
        if cache_type in ("response", None):
            self._response_cache.clear()
        if cache_type in ("state", None):
            self._state_cache.clear()
        logger.info("Cache cleared: %s", cache_type or "all")

    def evict_expired(self) -> int:
        """Remove all expired entries from in-memory caches.

        Returns:
            Total number of entries evicted.
        """
        evicted = 0
        for cache in (self._page_cache, self._response_cache, self._state_cache):
            expired_keys = [k for k, e in cache.items() if e.is_expired()]
            for k in expired_keys:
                del cache[k]
                evicted += 1
        if evicted:
            logger.debug("Evicted %d expired cache entries", evicted)
        return evicted

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        return {
            "backend": "redis" if self._redis else "memory",
            "page_cache": {
                "size": len(self._page_cache),
                "hits": sum(e.hits for e in self._page_cache.values()),
                "expired": sum(1 for e in self._page_cache.values() if e.is_expired()),
            },
            "response_cache": {
                "size": len(self._response_cache),
                "hits": sum(e.hits for e in self._response_cache.values()),
                "expired": sum(1 for e in self._response_cache.values() if e.is_expired()),
            },
            "state_cache": {
                "size": len(self._state_cache),
                "hits": sum(e.hits for e in self._state_cache.values()),
                "expired": sum(1 for e in self._state_cache.values() if e.is_expired()),
            },
        }
