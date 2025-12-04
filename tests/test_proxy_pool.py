"""Tests for proxy pool manager."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.core.browser.proxy_pool import (
    ProxyPool,
    Proxy,
    ProxyType,
    RotationStrategy,
)


def test_proxy_pool_initialization():
    """Test proxy pool initialization."""
    pool = ProxyPool()
    
    assert pool is not None
    assert len(pool.proxies) == 0
    assert pool.rotation_strategy == RotationStrategy.ROUND_ROBIN


def test_proxy_pool_initialization_with_proxies():
    """Test proxy pool initialization with proxy list."""
    proxies = ["http://proxy1:8080", "http://proxy2:8080"]
    pool = ProxyPool(proxies=proxies)
    
    assert len(pool.proxies) == 2
    assert pool.proxies[0].url == "http://proxy1:8080"
    assert pool.proxies[1].url == "http://proxy2:8080"


def test_add_proxy():
    """Test adding a single proxy."""
    pool = ProxyPool()
    
    proxy = pool.add_proxy("http://proxy1:8080")
    
    assert proxy is not None
    assert proxy.url == "http://proxy1:8080"
    assert proxy.proxy_type == ProxyType.HTTP
    assert len(pool.proxies) == 1


def test_add_proxy_https():
    """Test adding HTTPS proxy."""
    pool = ProxyPool()
    
    proxy = pool.add_proxy("https://proxy1:8443")
    
    assert proxy.proxy_type == ProxyType.HTTPS


def test_add_proxy_socks5():
    """Test adding SOCKS5 proxy."""
    pool = ProxyPool()
    
    proxy = pool.add_proxy("socks5://proxy1:1080")
    
    assert proxy.proxy_type == ProxyType.SOCKS5


def test_add_proxy_socks4():
    """Test adding SOCKS4 proxy."""
    pool = ProxyPool()
    
    proxy = pool.add_proxy("socks4://proxy1:1080")
    
    assert proxy.proxy_type == ProxyType.SOCKS4


def test_add_proxy_with_credentials():
    """Test adding proxy with username/password."""
    pool = ProxyPool()
    
    proxy = pool.add_proxy("http://proxy1:8080", username="user", password="pass")
    
    assert proxy.username == "user"
    assert proxy.password == "pass"


def test_add_proxies_batch():
    """Test adding multiple proxies at once."""
    pool = ProxyPool()
    
    proxy_urls = [
        "http://proxy1:8080",
        "http://proxy2:8080",
        "socks5://proxy3:1080",
    ]
    pool.add_proxies(proxy_urls)
    
    assert len(pool.proxies) == 3


def test_remove_proxy():
    """Test removing a proxy."""
    pool = ProxyPool(proxies=["http://proxy1:8080", "http://proxy2:8080"])
    
    result = pool.remove_proxy("http://proxy1:8080")
    
    assert result is True
    assert len(pool.proxies) == 1
    assert pool.proxies[0].url == "http://proxy2:8080"


def test_remove_proxy_not_found():
    """Test removing non-existent proxy."""
    pool = ProxyPool(proxies=["http://proxy1:8080"])
    
    result = pool.remove_proxy("http://nonexistent:8080")
    
    assert result is False
    assert len(pool.proxies) == 1


@pytest.mark.asyncio
async def test_get_proxy_round_robin():
    """Test round-robin proxy rotation."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"],
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
    )
    
    proxy1 = await pool.get_proxy()
    proxy2 = await pool.get_proxy()
    proxy3 = await pool.get_proxy()
    proxy4 = await pool.get_proxy()  # Should wrap around
    
    assert proxy1.url == "http://proxy1:8080"
    assert proxy2.url == "http://proxy2:8080"
    assert proxy3.url == "http://proxy3:8080"
    assert proxy4.url == "http://proxy1:8080"


@pytest.mark.asyncio
async def test_get_proxy_random():
    """Test random proxy rotation."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"],
        rotation_strategy=RotationStrategy.RANDOM,
    )
    
    proxies = [await pool.get_proxy() for _ in range(10)]
    
    # Should get proxies from the pool
    for proxy in proxies:
        assert proxy.url in ["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"]


@pytest.mark.asyncio
async def test_get_proxy_sticky():
    """Test sticky proxy rotation by domain."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080"],
        rotation_strategy=RotationStrategy.STICKY,
    )
    
    # Same domain should get same proxy
    proxy1 = await pool.get_proxy(domain="example.com")
    proxy2 = await pool.get_proxy(domain="example.com")
    proxy3 = await pool.get_proxy(domain="other.com")
    
    assert proxy1.url == proxy2.url
    # Different domain may get different proxy


@pytest.mark.asyncio
async def test_get_proxy_least_used():
    """Test least-used proxy rotation."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080"],
        rotation_strategy=RotationStrategy.LEAST_USED,
    )
    
    # Manually set usage counts
    pool.proxies[0].usage_count = 10
    pool.proxies[1].usage_count = 5
    
    proxy = await pool.get_proxy()
    
    # Should get least used proxy
    assert proxy.url == "http://proxy2:8080"


@pytest.mark.asyncio
async def test_get_proxy_empty_pool():
    """Test getting proxy from empty pool."""
    pool = ProxyPool()
    
    proxy = await pool.get_proxy()
    
    assert proxy is None


def test_proxy_mark_success():
    """Test marking proxy as successful."""
    proxy = Proxy(
        url="http://proxy1:8080",
        proxy_type=ProxyType.HTTP,
        failure_count=3,
        success_count=0,
        is_healthy=False,
    )
    
    proxy.mark_success()
    
    assert proxy.success_count == 1
    assert proxy.failure_count == 0
    assert proxy.is_healthy is True
    assert proxy.usage_count == 1
    assert proxy.last_used is not None


def test_proxy_mark_failure():
    """Test marking proxy as failed."""
    proxy = Proxy(
        url="http://proxy1:8080",
        proxy_type=ProxyType.HTTP,
        failure_count=0,
    )
    
    proxy.mark_failure()
    
    assert proxy.failure_count == 1
    assert proxy.is_healthy is True  # Still healthy after 1 failure
    
    # After 3 failures should be unhealthy
    proxy.mark_failure()
    proxy.mark_failure()
    
    assert proxy.failure_count == 3
    assert proxy.is_healthy is False


@pytest.mark.asyncio
async def test_unhealthy_proxy_excluded():
    """Test that unhealthy proxies are excluded from selection."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080"],
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
    )
    
    # Mark first proxy as unhealthy
    pool.proxies[0].is_healthy = False
    
    # Should only get healthy proxy
    for _ in range(5):
        proxy = await pool.get_proxy()
        assert proxy.url == "http://proxy2:8080"


@pytest.mark.asyncio
async def test_fallback_to_unhealthy_when_none_healthy():
    """Test fallback to unhealthy proxies when no healthy ones available."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080"],
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
    )
    
    # Mark all proxies as unhealthy
    pool.proxies[0].is_healthy = False
    
    # Should still return a proxy (fallback behavior)
    proxy = await pool.get_proxy()
    
    assert proxy is not None


def test_proxy_to_playwright_config():
    """Test Playwright configuration conversion."""
    proxy = Proxy(
        url="http://proxy1:8080",
        proxy_type=ProxyType.HTTP,
        username="user",
        password="pass",
    )
    
    config = proxy.to_playwright_config()
    
    assert "server" in config
    assert config["username"] == "user"
    assert config["password"] == "pass"


def test_proxy_to_playwright_config_no_auth():
    """Test Playwright config without auth."""
    proxy = Proxy(
        url="http://proxy1:8080",
        proxy_type=ProxyType.HTTP,
    )
    
    config = proxy.to_playwright_config()
    
    assert "server" in config
    assert "username" not in config
    assert "password" not in config


@pytest.mark.asyncio
async def test_health_check():
    """Test individual proxy health check."""
    pool = ProxyPool(proxies=["http://proxy1:8080"])
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await pool.health_check(pool.proxies[0])
        
        # Result depends on actual proxy - here we test the mock
        assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_health_check_all():
    """Test batch health checking."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080"],
    )
    
    with patch.object(pool, 'health_check', new_callable=AsyncMock) as mock_check:
        mock_check.side_effect = [True, False]
        
        results = await pool.health_check_all()
        
        assert len(results) == 2
        assert results["http://proxy1:8080"] is True
        assert results["http://proxy2:8080"] is False


def test_get_stats():
    """Test statistics retrieval."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080"],
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
    )
    
    # Make one proxy unhealthy
    pool.proxies[1].is_healthy = False
    
    stats = pool.get_stats()
    
    assert stats["total"] == 2
    assert stats["healthy"] == 1
    assert stats["unhealthy"] == 1
    assert stats["rotation_strategy"] == "round_robin"
    assert "proxies" in stats
    assert len(stats["proxies"]) == 2


def test_proxy_initialization_defaults():
    """Test proxy default values."""
    proxy = Proxy(
        url="http://proxy1:8080",
        proxy_type=ProxyType.HTTP,
    )
    
    assert proxy.is_healthy is True
    assert proxy.failure_count == 0
    assert proxy.success_count == 0
    assert proxy.usage_count == 0
    assert proxy.username is None
    assert proxy.password is None


def test_rotation_strategy_enum():
    """Test rotation strategy enum values."""
    assert RotationStrategy.ROUND_ROBIN.value == "round_robin"
    assert RotationStrategy.RANDOM.value == "random"
    assert RotationStrategy.STICKY.value == "sticky"
    assert RotationStrategy.LEAST_USED.value == "least_used"


def test_proxy_type_enum():
    """Test proxy type enum values."""
    assert ProxyType.HTTP.value == "http"
    assert ProxyType.HTTPS.value == "https"
    assert ProxyType.SOCKS4.value == "socks4"
    assert ProxyType.SOCKS5.value == "socks5"


@pytest.mark.asyncio
async def test_concurrent_get_proxy():
    """Test thread-safety of get_proxy under concurrent access."""
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"],
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
    )
    
    async def get_proxy_task():
        return await pool.get_proxy()
    
    # Run multiple concurrent requests
    tasks = [get_proxy_task() for _ in range(10)]
    results = await asyncio.gather(*tasks)
    
    # All should succeed and return valid proxies
    for proxy in results:
        assert proxy is not None
        assert proxy.url in ["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"]

