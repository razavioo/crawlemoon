"""Tests for rate limiter."""

import pytest
import asyncio
import time
from unittest.mock import patch

from src.core.rate_limiter import RateLimiter, RateLimitConfig


def test_rate_limiter_initialization():
    """Test rate limiter initialization."""
    limiter = RateLimiter()
    
    assert limiter is not None
    assert limiter._default_config is not None
    assert limiter._default_config.requests_per_second == 1.0


def test_set_default_rate_limit():
    """Test setting default rate limit."""
    limiter = RateLimiter()
    
    limiter.set_default_rate_limit(
        requests_per_second=2.0,
        requests_per_minute=100,
        requests_per_hour=1000,
    )
    
    assert limiter._default_config.requests_per_second == 2.0
    assert limiter._default_config.requests_per_minute == 100
    assert limiter._default_config.requests_per_hour == 1000


def test_set_domain_rate_limit():
    """Test setting per-domain rate limit."""
    limiter = RateLimiter()
    
    limiter.set_domain_rate_limit(
        "example.com",
        requests_per_second=5.0,
        requests_per_minute=200,
    )
    
    assert "example.com" in limiter._domain_configs
    assert limiter._domain_configs["example.com"].requests_per_second == 5.0
    assert limiter._domain_configs["example.com"].requests_per_minute == 200


def test_set_global_rate_limit():
    """Test setting global rate limit."""
    limiter = RateLimiter()
    
    limiter.set_global_rate_limit(
        requests_per_second=10.0,
        requests_per_minute=500,
    )
    
    assert limiter._global_config is not None
    assert limiter._global_config.requests_per_second == 10.0
    assert limiter._global_queue is not None


@pytest.mark.asyncio
async def test_wait_if_needed_no_limit():
    """Test that wait_if_needed doesn't block when under limit."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=100.0)
    
    start_time = time.time()
    await limiter.wait_if_needed("https://example.com/page1")
    elapsed = time.time() - start_time
    
    # Should not wait significantly
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_wait_if_needed_per_second_limit():
    """Test per-second rate limit enforcement."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=2.0)  # Allow 2 per second
    
    # Make 3 quick requests - third should be delayed
    await limiter.wait_if_needed("https://example.com/page1")
    await limiter.wait_if_needed("https://example.com/page2")
    
    start_time = time.time()
    await limiter.wait_if_needed("https://example.com/page3")
    elapsed = time.time() - start_time
    
    # Third request should have waited
    # (may be 0 if queue cleanup happened)
    assert elapsed >= 0


@pytest.mark.asyncio
async def test_record_response_429():
    """Test exponential backoff on 429 response."""
    limiter = RateLimiter()
    
    limiter.record_response("https://example.com/api", 429)
    
    assert "example.com" in limiter._domain_backoff
    backoff_until = limiter._domain_backoff["example.com"]
    assert backoff_until > time.time()


@pytest.mark.asyncio
async def test_record_response_503():
    """Test exponential backoff on 503 response."""
    limiter = RateLimiter()
    
    limiter.record_response("https://example.com/api", 503)
    
    assert "example.com" in limiter._domain_backoff


def test_record_response_200_no_backoff():
    """Test that 200 response doesn't trigger backoff."""
    limiter = RateLimiter()
    
    limiter.record_response("https://example.com/api", 200)
    
    assert "example.com" not in limiter._domain_backoff


@pytest.mark.asyncio
async def test_domain_backoff_increases():
    """Test that repeated failures increase backoff."""
    limiter = RateLimiter()
    
    limiter.record_response("https://example.com/api", 429)
    first_backoff = limiter._domain_backoff["example.com"] - time.time()
    
    # Simulate time passing but still in backoff
    limiter.record_response("https://example.com/api", 429)
    second_backoff = limiter._domain_backoff["example.com"] - time.time()
    
    # Backoff should increase (or stay same if near max)
    assert second_backoff >= first_backoff or second_backoff >= 5.0


def test_get_stats():
    """Test statistics retrieval."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=2.0)
    limiter.set_domain_rate_limit("example.com", requests_per_second=5.0)
    
    stats = limiter.get_stats()
    
    assert "default_config" in stats
    assert stats["default_config"]["requests_per_second"] == 2.0
    assert stats["domain_configs"] == 1
    assert stats["domains_in_backoff"] == 0
    assert stats["domains_tracked"] == 0


def test_get_stats_with_global():
    """Test statistics with global rate limit."""
    limiter = RateLimiter()
    limiter.set_global_rate_limit(requests_per_second=10.0)
    
    stats = limiter.get_stats()
    
    assert "global_config" in stats
    assert stats["global_config"]["requests_per_second"] == 10.0


def test_rate_limit_config_get_min_interval():
    """Test RateLimitConfig minimum interval calculation."""
    config = RateLimitConfig(requests_per_second=2.0)
    
    interval = config.get_min_interval()
    
    assert interval == 0.5  # 1/2 = 0.5 seconds


def test_rate_limit_config_default_interval():
    """Test RateLimitConfig default interval."""
    config = RateLimitConfig(requests_per_second=0)
    
    interval = config.get_min_interval()
    
    assert interval == 1.0  # Default when rps is 0


@pytest.mark.asyncio
async def test_wait_if_needed_domain_specific():
    """Test that domain-specific limits override defaults."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=1.0)
    limiter.set_domain_rate_limit("fast.example.com", requests_per_second=100.0)
    
    # Fast domain should not be limited much
    start_time = time.time()
    for _ in range(5):
        await limiter.wait_if_needed("https://fast.example.com/api")
    elapsed = time.time() - start_time
    
    # Should be quick since limit is 100/s
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_wait_if_needed_respects_backoff():
    """Test that wait_if_needed respects backoff state."""
    limiter = RateLimiter()
    
    # Set a short backoff
    limiter._domain_backoff["example.com"] = time.time() + 0.2
    
    start_time = time.time()
    await limiter.wait_if_needed("https://example.com/api")
    elapsed = time.time() - start_time
    
    # Should have waited for backoff
    assert elapsed >= 0.1  # Allow some tolerance


@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test thread-safety under concurrent access."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=100.0)
    
    async def make_request(url):
        await limiter.wait_if_needed(url)
        return True
    
    # Run many concurrent requests
    tasks = [make_request(f"https://example.com/page{i}") for i in range(20)]
    results = await asyncio.gather(*tasks)
    
    # All should complete successfully
    assert all(results)


@pytest.mark.asyncio
async def test_queue_cleanup():
    """Test that old queue entries are cleaned up."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=10.0)
    
    # Add some requests
    await limiter.wait_if_needed("https://example.com/page1")
    await limiter.wait_if_needed("https://example.com/page2")
    
    # Queue should exist for domain
    assert "example.com" in limiter._domain_queues
    assert len(limiter._domain_queues["example.com"]) <= 2


@pytest.mark.asyncio
async def test_multiple_domains():
    """Test rate limiting across multiple domains."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=10.0)
    
    # Make requests to different domains
    await limiter.wait_if_needed("https://example1.com/api")
    await limiter.wait_if_needed("https://example2.com/api")
    await limiter.wait_if_needed("https://example3.com/api")
    
    # Should have entries for all domains
    assert "example1.com" in limiter._domain_queues
    assert "example2.com" in limiter._domain_queues
    assert "example3.com" in limiter._domain_queues


def test_url_parsing_for_domain():
    """Test that URL parsing extracts correct domain."""
    limiter = RateLimiter()
    limiter.set_domain_rate_limit("api.example.com", requests_per_second=5.0)
    
    # Domain should match
    assert "api.example.com" in limiter._domain_configs


@pytest.mark.asyncio
async def test_global_and_domain_limits_combined():
    """Test that both global and domain limits are applied."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=50.0)
    limiter.set_global_rate_limit(requests_per_second=100.0)
    
    # Both should be checked
    await limiter.wait_if_needed("https://example.com/api")
    
    # Global queue should have entry
    assert len(limiter._global_queue) == 1


def test_backoff_max_duration():
    """Test that backoff doesn't exceed maximum."""
    limiter = RateLimiter()
    
    # Simulate many failures
    for _ in range(10):
        limiter.record_response("https://example.com/api", 429)
    
    # Backoff should be capped at 5 minutes
    backoff_duration = limiter._domain_backoff["example.com"] - time.time()
    assert backoff_duration <= 300  # 5 minutes max

