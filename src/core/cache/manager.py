"""Cache Manager with TTL support."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from dataclasses import dataclass
import json

from cachetools import TTLCache

logger = logging.getLogger(__name__)


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


class CacheManager:
    """Manages caching for pages, responses, and state snapshots."""
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl_seconds: int = 3600,
    ):
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        
        # Separate caches for different types
        self._page_cache: Dict[str, CacheEntry] = {}
        self._response_cache: Dict[str, CacheEntry] = {}
        self._state_cache: Dict[str, CacheEntry] = {}
    
    def _generate_key(self, url: str, **params) -> str:
        """Generate cache key from URL and parameters."""
        key_data = {"url": url, **params}
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def get_page(self, url: str, **params) -> Optional[Any]:
        """Get cached page content."""
        key = self._generate_key(url, **params)
        entry = self._page_cache.get(key)
        
        if not entry:
            return None
        
        if entry.is_expired():
            del self._page_cache[key]
            return None
        
        entry.access()
        logger.debug(f"Page cache hit: {url}")
        return entry.value
    
    def set_page(
        self,
        url: str,
        content: Any,
        ttl_seconds: Optional[int] = None,
        **params
    ) -> None:
        """Cache page content."""
        key = self._generate_key(url, **params)
        ttl = ttl_seconds or self.default_ttl_seconds
        
        entry = CacheEntry(
            key=key,
            value=content,
            created_at=datetime.now(),
            ttl_seconds=ttl,
        )
        
        # Remove oldest if cache is full
        if len(self._page_cache) >= self.max_size:
            oldest_key = min(
                self._page_cache.keys(),
                key=lambda k: self._page_cache[k].created_at
            )
            del self._page_cache[oldest_key]
        
        self._page_cache[key] = entry
        logger.debug(f"Page cached: {url}")
    
    def get_response(self, url: str, method: str = "GET", **params) -> Optional[Any]:
        """Get cached API response."""
        key = self._generate_key(url, method=method, **params)
        entry = self._response_cache.get(key)
        
        if not entry:
            return None
        
        if entry.is_expired():
            del self._response_cache[key]
            return None
        
        entry.access()
        logger.debug(f"Response cache hit: {url}")
        return entry.value
    
    def set_response(
        self,
        url: str,
        response: Any,
        method: str = "GET",
        ttl_seconds: Optional[int] = None,
        **params
    ) -> None:
        """Cache API response."""
        key = self._generate_key(url, method=method, **params)
        ttl = ttl_seconds or self.default_ttl_seconds
        
        entry = CacheEntry(
            key=key,
            value=response,
            created_at=datetime.now(),
            ttl_seconds=ttl,
        )
        
        if len(self._response_cache) >= self.max_size:
            oldest_key = min(
                self._response_cache.keys(),
                key=lambda k: self._response_cache[k].created_at
            )
            del self._response_cache[oldest_key]
        
        self._response_cache[key] = entry
        logger.debug(f"Response cached: {url}")
    
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
        ttl_seconds: Optional[int] = None
    ) -> None:
        """Cache state snapshot."""
        ttl = ttl_seconds or (self.default_ttl_seconds * 24)  # Longer TTL for states
        
        entry = CacheEntry(
            key=snapshot_id,
            value=state,
            created_at=datetime.now(),
            ttl_seconds=ttl,
        )
        
        if len(self._state_cache) >= self.max_size:
            oldest_key = min(
                self._state_cache.keys(),
                key=lambda k: self._state_cache[k].created_at
            )
            del self._state_cache[oldest_key]
        
        self._state_cache[snapshot_id] = entry
        logger.debug(f"State snapshot cached: {snapshot_id}")
    
    def clear(self, cache_type: Optional[str] = None) -> None:
        """Clear cache(s)."""
        if cache_type == "page" or cache_type is None:
            self._page_cache.clear()
        if cache_type == "response" or cache_type is None:
            self._response_cache.clear()
        if cache_type == "state" or cache_type is None:
            self._state_cache.clear()
        
        logger.info(f"Cache cleared: {cache_type or 'all'}")
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        return {
            "page_cache": {
                "size": len(self._page_cache),
                "hits": sum(e.hits for e in self._page_cache.values()),
            },
            "response_cache": {
                "size": len(self._response_cache),
                "hits": sum(e.hits for e in self._response_cache.values()),
            },
            "state_cache": {
                "size": len(self._state_cache),
                "hits": sum(e.hits for e in self._state_cache.values()),
            },
        }


