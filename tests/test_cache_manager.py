"""Tests for cache manager."""

import pytest
import time
from datetime import datetime, timedelta

from src.core.cache.manager import CacheManager, CacheEntry


def test_cache_entry_creation():
    """Test cache entry creation."""
    entry = CacheEntry(
        key="test_key",
        value="test_value",
        created_at=datetime.now(),
        ttl_seconds=60,
    )
    
    assert entry.key == "test_key"
    assert entry.value == "test_value"
    assert entry.hits == 0
    assert entry.is_expired() is False


def test_cache_entry_expiration():
    """Test cache entry expiration."""
    entry = CacheEntry(
        key="test_key",
        value="test_value",
        created_at=datetime.now() - timedelta(seconds=61),
        ttl_seconds=60,
    )
    
    assert entry.is_expired() is True


def test_cache_entry_access():
    """Test cache entry access tracking."""
    entry = CacheEntry(
        key="test_key",
        value="test_value",
        created_at=datetime.now(),
        ttl_seconds=60,
    )
    
    assert entry.hits == 0
    assert entry.last_accessed is None
    
    entry.access()
    
    assert entry.hits == 1
    assert entry.last_accessed is not None


def test_cache_manager_initialization(cache_manager):
    """Test cache manager initialization."""
    assert cache_manager.max_size == 100
    assert cache_manager.default_ttl_seconds == 60


def test_cache_manager_set_get_page(cache_manager):
    """Test setting and getting page cache."""
    url = "https://example.com"
    content = "<html>Test</html>"
    
    # Should not exist initially
    assert cache_manager.get_page(url) is None
    
    # Set cache
    cache_manager.set_page(url, content)
    
    # Should exist now
    cached = cache_manager.get_page(url)
    assert cached == content


def test_cache_manager_set_get_response(cache_manager):
    """Test setting and getting response cache."""
    url = "https://api.example.com/data"
    response = {"data": "test"}
    
    assert cache_manager.get_response(url) is None
    
    cache_manager.set_response(url, response, method="GET")
    
    cached = cache_manager.get_response(url, method="GET")
    assert cached == response


def test_cache_manager_ttl(cache_manager):
    """Test cache TTL expiration."""
    url = "https://example.com"
    content = "<html>Test</html>"
    
    cache_manager.set_page(url, content, ttl_seconds=1)
    
    # Should exist immediately
    assert cache_manager.get_page(url) == content
    
    # Wait for expiration
    time.sleep(1.1)
    
    # Should be expired
    assert cache_manager.get_page(url) is None


def test_cache_manager_max_size(cache_manager):
    """Test cache respects max size."""
    cache_manager.max_size = 3
    
    # Fill cache
    for i in range(5):
        cache_manager.set_page(f"https://example{i}.com", f"content{i}")
    
    # Should only have max_size entries
    stats = cache_manager.get_stats()
    assert stats["page_cache"]["size"] <= cache_manager.max_size


def test_cache_manager_clear(cache_manager):
    """Test clearing cache."""
    cache_manager.set_page("https://example.com", "content")
    cache_manager.set_response("https://api.example.com", {"data": "test"})
    
    assert cache_manager.get_page("https://example.com") is not None
    assert cache_manager.get_response("https://api.example.com") is not None
    
    cache_manager.clear()
    
    assert cache_manager.get_page("https://example.com") is None
    assert cache_manager.get_response("https://api.example.com") is None


def test_cache_manager_clear_specific(cache_manager):
    """Test clearing specific cache type."""
    cache_manager.set_page("https://example.com", "content")
    cache_manager.set_response("https://api.example.com", {"data": "test"})
    
    cache_manager.clear("page")
    
    assert cache_manager.get_page("https://example.com") is None
    assert cache_manager.get_response("https://api.example.com") is not None


def test_cache_manager_stats(cache_manager):
    """Test cache statistics."""
    cache_manager.set_page("https://example.com", "content")
    cache_manager.get_page("https://example.com")  # Hit
    
    stats = cache_manager.get_stats()
    
    assert "page_cache" in stats
    assert "response_cache" in stats
    assert "state_cache" in stats
    assert stats["page_cache"]["size"] == 1
    assert stats["page_cache"]["hits"] == 1


def test_cache_manager_state_snapshot(cache_manager):
    """Test state snapshot caching."""
    snapshot_id = "snapshot_123"
    state = {"url": "https://example.com", "cookies": {}}
    
    assert cache_manager.get_state_snapshot(snapshot_id) is None
    
    cache_manager.set_state_snapshot(snapshot_id, state)
    
    cached = cache_manager.get_state_snapshot(snapshot_id)
    assert cached == state


def test_cache_manager_key_generation(cache_manager):
    """Test cache key generation with parameters."""
    url = "https://example.com"
    content1 = "content1"
    content2 = "content2"
    
    cache_manager.set_page(url, content1, param1="value1")
    cache_manager.set_page(url, content2, param1="value2")
    
    assert cache_manager.get_page(url, param1="value1") == content1
    assert cache_manager.get_page(url, param1="value2") == content2

