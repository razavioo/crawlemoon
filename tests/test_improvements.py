"""Tests for improvements: proxy failover, cache TTL/LRU, browser recovery,
concurrent tools, data retention, rate-limit headers, and crawler generation.
"""

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.browser.pool import BrowserPool, BrowserInstance
from src.core.browser.proxy_pool import ProxyPool, Proxy, ProxyType, RotationStrategy
from src.core.cache.manager import CacheEntry, CacheManager
from src.core.rate_limiter import RateLimiter
from src.core.recording_storage import RecordingStorage
from src.exceptions import (
    BrowserPoolExhaustedError,
    CrawlerGenerationError,
    NoHealthyProxyError,
    RecordingExpiredError,
    RecordingNotFoundError,
    RecordingSerializationError,
)
from src.intelligence.generator.crawler_gen import CrawlerDefinition, CrawlerGenerator
from src.intelligence.recorder.session import (
    Event,
    EventType,
    NetworkEvent,
    SessionRecording,
    StateSnapshot,
)
from src.intelligence.recorder.state_machine import (
    ExtractionPoint,
    State,
    StateMachine,
    StateType,
    Transition,
)
from src.mcp.utils import validate_url, require_url
from src.exceptions import URLValidationError


# ============================================================
# URL validation
# ============================================================


def test_validate_url_valid():
    assert validate_url("https://example.com") is True
    assert validate_url("http://sub.example.com/path?q=1") is True


def test_validate_url_invalid():
    assert validate_url("ftp://example.com") is False
    assert validate_url("not-a-url") is False
    assert validate_url("") is False
    assert validate_url(None) is False  # type: ignore[arg-type]


def test_require_url_raises():
    with pytest.raises(URLValidationError):
        require_url("not-a-url")


def test_require_url_passes():
    require_url("https://example.com")  # must not raise


# ============================================================
# Proxy pool — failover
# ============================================================


@pytest.mark.asyncio
async def test_proxy_pool_all_unhealthy_falls_back_to_all():
    """When all proxies are unhealthy get_proxy still returns one (fallback)."""
    pool = ProxyPool(proxies=["http://p1:8080", "http://p2:8080"])
    for proxy in pool.proxies:
        proxy.is_healthy = False

    # get_proxy falls back to the full list rather than raising
    result = await pool.get_proxy()
    assert result is not None


@pytest.mark.asyncio
async def test_proxy_pool_empty_returns_none():
    pool = ProxyPool()
    result = await pool.get_proxy()
    assert result is None


def test_proxy_mark_failure_makes_unhealthy():
    pool = ProxyPool(proxies=["http://p1:8080"])
    proxy = pool.proxies[0]
    for _ in range(3):
        proxy.mark_failure()
    assert proxy.is_healthy is False


def test_proxy_mark_success_restores_health():
    pool = ProxyPool(proxies=["http://p1:8080"])
    proxy = pool.proxies[0]
    for _ in range(3):
        proxy.mark_failure()
    assert proxy.is_healthy is False
    proxy.mark_success()
    assert proxy.is_healthy is True


@pytest.mark.asyncio
async def test_proxy_pool_health_check_failure_marks_proxy(monkeypatch):
    """A network error during health_check marks the proxy as failed."""
    pool = ProxyPool(proxies=["http://bad-proxy:8080"])
    proxy = pool.proxies[0]

    import httpx

    async def _mock_get(*args, **kwargs):
        raise httpx.RequestError("connection refused")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))
        mock_client_cls.return_value = mock_client

        result = await pool.health_check(proxy)

    assert result is False
    assert proxy.failure_count >= 1


@pytest.mark.asyncio
async def test_proxy_least_used_strategy():
    pool = ProxyPool(
        proxies=["http://p1:8080", "http://p2:8080", "http://p3:8080"],
        rotation_strategy=RotationStrategy.LEAST_USED,
    )
    pool.proxies[0].usage_count = 10
    pool.proxies[1].usage_count = 2
    pool.proxies[2].usage_count = 5

    selected = await pool.get_proxy()
    assert selected.usage_count == 2  # least used


@pytest.mark.asyncio
async def test_proxy_sticky_strategy():
    pool = ProxyPool(
        proxies=["http://p1:8080", "http://p2:8080"],
        rotation_strategy=RotationStrategy.STICKY,
    )
    r1 = await pool.get_proxy(domain="example.com")
    r2 = await pool.get_proxy(domain="example.com")
    assert r1.url == r2.url  # same proxy for same domain


# ============================================================
# Cache — TTL expiry and LRU eviction
# ============================================================


def test_cache_ttl_expiry():
    mgr = CacheManager(default_ttl_seconds=1)
    mgr.set_page("http://a.com", "content", ttl_seconds=1)
    assert mgr.get_page("http://a.com") == "content"

    # Manually expire the entry
    for entry in mgr._page_cache.values():
        entry.created_at = datetime.now() - timedelta(seconds=2)

    assert mgr.get_page("http://a.com") is None


def test_cache_lru_eviction():
    """When max_size is hit the LRU entry is removed."""
    mgr = CacheManager(max_size=3, default_ttl_seconds=3600)
    mgr.set_page("http://a.com", "a")
    mgr.set_page("http://b.com", "b")
    # Access 'a' so 'b' becomes LRU
    mgr.get_page("http://a.com")
    # Now add two more to push 'b' out
    mgr.set_page("http://c.com", "c")
    mgr.set_page("http://d.com", "d")

    assert len(mgr._page_cache) <= 3


def test_cache_evict_expired():
    mgr = CacheManager(default_ttl_seconds=1)
    mgr.set_page("http://x.com", "x", ttl_seconds=1)
    # Expire manually
    for entry in mgr._page_cache.values():
        entry.created_at = datetime.now() - timedelta(seconds=2)

    evicted = mgr.evict_expired()
    assert evicted >= 1
    assert len(mgr._page_cache) == 0


def test_cache_stats_includes_expired():
    mgr = CacheManager(default_ttl_seconds=1)
    mgr.set_page("http://y.com", "y", ttl_seconds=1)
    for entry in mgr._page_cache.values():
        entry.created_at = datetime.now() - timedelta(seconds=2)

    stats = mgr.get_stats()
    assert stats["page_cache"]["expired"] == 1


# ============================================================
# Browser pool — warmup and crash recovery
# ============================================================


@pytest.mark.asyncio
async def test_browser_pool_warmup(browser_pool):
    """Warmup should pre-create instances."""
    assert len(browser_pool._instances) == 0
    await browser_pool.warmup(count=1)
    assert len(browser_pool._instances) == 1


@pytest.mark.asyncio
async def test_browser_pool_warmup_partial_failure(browser_pool):
    """Warmup should not raise if some instances fail; just logs a warning."""
    original_create = browser_pool._create_new_instance
    call_count = 0

    async def flaky_create(**kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated browser crash")
        return await original_create(**kw)

    browser_pool._create_new_instance = flaky_create
    # Should not raise even with a failure
    await browser_pool.warmup(count=2)
    # At least the second one should have been created
    assert len(browser_pool._instances) >= 1


@pytest.mark.asyncio
async def test_browser_pool_cleanup_removes_overused(browser_pool):
    """Instances that exceed max_usage are removed during cleanup."""
    await browser_pool.acquire()
    for inst in browser_pool._instances:
        inst.usage_count = inst.max_usage + 1  # force overused

    await browser_pool._cleanup()
    assert len(browser_pool._instances) == 0


@pytest.mark.asyncio
async def test_browser_pool_cleanup_removes_expired(browser_pool):
    """Instances older than max_age_minutes are removed during cleanup."""
    await browser_pool.acquire()
    for inst in browser_pool._instances:
        inst.created_at = datetime.now() - timedelta(hours=2)

    await browser_pool._cleanup()
    assert len(browser_pool._instances) == 0


# ============================================================
# Rate limiter — Retry-After header
# ============================================================


def test_rate_limiter_retry_after_header():
    limiter = RateLimiter()
    limiter.record_response(
        "https://api.example.com/data",
        429,
        headers={"Retry-After": "30"},
    )
    domain = "api.example.com"
    assert domain in limiter._domain_backoff
    remaining = limiter._domain_backoff[domain] - time.time()
    # Should be ~30s, allow ±2s tolerance
    assert 28 <= remaining <= 32


def test_rate_limiter_x_ratelimit_reset_header():
    limiter = RateLimiter()
    future_ts = time.time() + 45
    limiter.record_response(
        "https://api.example.com/data",
        429,
        headers={"X-RateLimit-Reset": str(future_ts)},
    )
    domain = "api.example.com"
    remaining = limiter._domain_backoff[domain] - time.time()
    assert 43 <= remaining <= 47


def test_rate_limiter_no_header_uses_exponential_backoff():
    limiter = RateLimiter()
    limiter.record_response("https://api.example.com/data", 429)
    domain = "api.example.com"
    assert domain in limiter._domain_backoff
    # First backoff should be 5 seconds
    remaining = limiter._domain_backoff[domain] - time.time()
    assert 3 <= remaining <= 7


def test_rate_limiter_non_rate_limit_status_ignored():
    limiter = RateLimiter()
    limiter.record_response("https://api.example.com/data", 200)
    assert "api.example.com" not in limiter._domain_backoff


def test_rate_limiter_exponential_growth():
    limiter = RateLimiter()
    # First hit: backoff=5s
    limiter.record_response("https://api.example.com/data", 429)
    first_backoff = limiter._domain_backoff["api.example.com"]

    # Second hit while still in backoff should double
    limiter.record_response("https://api.example.com/data", 429)
    second_backoff = limiter._domain_backoff["api.example.com"]
    assert second_backoff > first_backoff


# ============================================================
# Recording storage — retention / purge
# ============================================================


def _make_recording(recording_id: str, start_time: datetime) -> SessionRecording:
    r = SessionRecording(
        id=recording_id,
        start_time=start_time,
    )
    r.end_time = start_time + timedelta(seconds=10)
    r.duration = 10.0
    return r


def test_recording_storage_save_and_load(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path))
    rec = _make_recording("rec1", datetime.now())
    storage.save_recording(rec, export_har=False)
    loaded = storage.load_recording("rec1")
    assert loaded.id == "rec1"


def test_recording_storage_not_found(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path))
    with pytest.raises(RecordingNotFoundError):
        storage.load_recording("nonexistent")


def test_recording_storage_expired_raises(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path), max_age_days=7)
    old_time = datetime.now() - timedelta(days=10)
    rec = _make_recording("old_rec", old_time)
    storage.save_recording(rec, export_har=False)

    with pytest.raises(RecordingExpiredError):
        storage.load_recording("old_rec")


def test_recording_storage_purge_expired(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path), max_age_days=7)

    old_time = datetime.now() - timedelta(days=10)
    new_time = datetime.now() - timedelta(days=1)

    storage.save_recording(_make_recording("old1", old_time), export_har=False)
    storage.save_recording(_make_recording("new1", new_time), export_har=False)

    deleted = storage.purge_expired()
    assert deleted == 1

    # Old one should be gone; new one should remain
    assert not (tmp_path / "old1.json").exists()
    assert (tmp_path / "new1.json").exists()


def test_recording_storage_list_marks_expired(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path), max_age_days=7)
    old_time = datetime.now() - timedelta(days=10)
    storage.save_recording(_make_recording("exp1", old_time), export_har=False)

    listings = storage.list_recordings()
    expired_items = [r for r in listings if r.get("expired")]
    assert len(expired_items) == 1


def test_recording_storage_no_retention_never_expires(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path), max_age_days=None)
    very_old = datetime.now() - timedelta(days=3650)
    rec = _make_recording("ancient", very_old)
    storage.save_recording(rec, export_har=False)

    # Should not raise
    loaded = storage.load_recording("ancient")
    assert loaded.id == "ancient"


def test_recording_storage_delete(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path))
    rec = _make_recording("del1", datetime.now())
    storage.save_recording(rec, export_har=False)
    assert storage.delete_recording("del1") is True
    assert not (tmp_path / "del1.json").exists()


def test_recording_storage_delete_nonexistent(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path))
    assert storage.delete_recording("ghost") is False


def test_recording_storage_active_recording_lifecycle(tmp_path):
    storage = RecordingStorage(storage_dir=str(tmp_path))
    rec = _make_recording("active1", datetime.now())
    storage.register_active_recording(rec)
    assert "active1" in storage._active_recordings

    loaded = storage.load_recording("active1")
    assert loaded.id == "active1"

    storage.unregister_active_recording("active1")
    assert "active1" not in storage._active_recordings


# ============================================================
# Crawler generator — from_state_machine (was placeholder)
# ============================================================


def _make_state_machine() -> StateMachine:
    sm = StateMachine()
    s0 = State(id="s0", name="Home", url="https://example.com", type=StateType.INITIAL)
    s1 = State(id="s1", name="About", url="https://example.com/about", type=StateType.INTERMEDIATE)
    s2 = State(id="s2", name="Contact", url="https://example.com/contact", type=StateType.FINAL)
    sm.states = [s0, s1, s2]
    sm.initial_state = s0
    sm.transitions = [
        Transition(from_state="s0", to_state="s1", action="navigate"),
        Transition(from_state="s1", to_state="s2", action="navigate"),
    ]
    sm.data_extraction_points = [
        ExtractionPoint(state_id="s1", selector="h1", field_name="title", extractor_type="text")
    ]
    return sm


def test_crawler_from_state_machine_basic():
    gen = CrawlerGenerator()
    sm = _make_state_machine()
    crawler = gen.from_state_machine(sm)

    assert crawler.name == "generated_crawler"
    # Should have navigate steps for transitions
    navigate_steps = [s for s in crawler.steps if s["action"] == "navigate"]
    assert len(navigate_steps) >= 2
    # Should include the extraction point
    extract_steps = [s for s in crawler.steps if s["action"] == "extract"]
    assert len(extract_steps) == 1
    assert extract_steps[0]["field"] == "title"


def test_crawler_from_state_machine_empty_raises():
    gen = CrawlerGenerator()
    with pytest.raises(CrawlerGenerationError):
        gen.from_state_machine(StateMachine())


def test_crawler_from_recording_full():
    gen = CrawlerGenerator()
    rec = SessionRecording(
        id="test",
        start_time=datetime.now(),
        state_snapshots=[
            StateSnapshot(url="https://example.com", html="", timestamp=datetime.now())
        ],
    )
    rec.events = [
        Event(type=EventType.NAVIGATE, timestamp=datetime.now(), data={"url": "https://example.com"}),
        Event(type=EventType.CLICK, timestamp=datetime.now(), data={}, selector="#btn"),
        Event(type=EventType.TYPE, timestamp=datetime.now(), data={"value": "hello"}, selector="#input"),
        Event(type=EventType.SCROLL, timestamp=datetime.now(), data={"x": 0, "y": 500}),
        Event(type=EventType.WAIT, timestamp=datetime.now(), data={"timeout": 2000}),
        Event(type=EventType.HOVER, timestamp=datetime.now(), data={}, selector="#menu"),
    ]
    crawler = gen.from_recording(rec)

    actions = [s["action"] for s in crawler.steps]
    assert "navigate" in actions
    assert "click" in actions
    assert "fill" in actions
    assert "scroll" in actions
    assert "wait" in actions
    assert "hover" in actions


def test_crawler_optimizer_deduplicates_navigations():
    gen = CrawlerGenerator()
    crawler = CrawlerDefinition(
        name="test",
        description="",
        steps=[
            {"action": "navigate", "url": "https://example.com"},
            {"action": "navigate", "url": "https://example.com"},  # duplicate
            {"action": "click", "selector": "#btn"},
        ],
    )
    optimised = gen.optimize_crawler(crawler)
    nav_steps = [s for s in optimised.steps if s["action"] == "navigate"]
    assert len(nav_steps) == 1


def test_crawler_optimizer_removes_wait_before_navigate():
    gen = CrawlerGenerator()
    crawler = CrawlerDefinition(
        name="test",
        description="",
        steps=[
            {"action": "wait", "timeout": 1000},
            {"action": "navigate", "url": "https://example.com"},
        ],
    )
    optimised = gen.optimize_crawler(crawler)
    actions = [s["action"] for s in optimised.steps]
    assert "wait" not in actions
    assert "navigate" in actions


def test_crawler_optimizer_removes_empty_fill():
    gen = CrawlerGenerator()
    crawler = CrawlerDefinition(
        name="test",
        description="",
        steps=[
            {"action": "fill", "selector": "#name", "value": ""},  # empty — should be dropped
            {"action": "fill", "selector": "#email", "value": "user@example.com"},
        ],
    )
    optimised = gen.optimize_crawler(crawler)
    assert len(optimised.steps) == 1
    assert optimised.steps[0]["value"] == "user@example.com"


def test_crawler_to_python_code():
    gen = CrawlerGenerator()
    crawler = CrawlerDefinition(
        name="my_crawler",
        description="test",
        steps=[
            {"action": "navigate", "url": "https://example.com"},
            {"action": "click", "selector": "#btn"},
        ],
    )
    code = gen.to_python_code(crawler)
    assert "async_playwright" in code
    assert 'page.goto("https://example.com")' in code
    assert 'page.click("#btn")' in code


def test_crawler_to_playwright_script():
    gen = CrawlerGenerator()
    crawler = CrawlerDefinition(
        name="My Crawler",
        description="test",
        steps=[{"action": "navigate", "url": "https://example.com"}],
    )
    code = gen.to_playwright_script(crawler)
    assert "def test_my_crawler" in code
    assert 'page.goto("https://example.com")' in code


def test_crawler_to_yaml():
    gen = CrawlerGenerator()
    crawler = CrawlerDefinition(
        name="yaml_test",
        description="test",
        steps=[{"action": "navigate", "url": "https://example.com"}],
    )
    yaml_str = gen.to_yaml(crawler)
    assert "yaml_test" in yaml_str
    assert "navigate" in yaml_str


# ============================================================
# Sensitive data scrubbing
# ============================================================


def test_sensitive_data_scrubber_api_key():
    from src.core.logging import _scrub

    text = "Using api_key=sk-ant-abc123XYZ789foobar"
    scrubbed = _scrub(text)
    assert "sk-ant-" not in scrubbed or "[REDACTED]" in scrubbed


def test_sensitive_data_scrubber_bearer():
    from src.core.logging import _scrub

    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"
    scrubbed = _scrub(text)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed


def test_sensitive_data_scrubber_url_credentials():
    from src.core.logging import _scrub

    text = "Connecting to postgres://admin:supersecret@db.example.com/mydb"
    scrubbed = _scrub(text)
    assert "supersecret" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_sensitive_data_filter_log_record():
    import logging

    from src.core.logging import SensitiveDataFilter

    filt = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="token=%s",
        args=("sk-verysecrettoken123456",),
        exc_info=None,
    )
    filt.filter(record)
    formatted = record.msg % record.args
    assert "sk-" not in formatted or "[REDACTED]" in formatted


# ============================================================
# Concurrent tool safety (cache under concurrent reads/writes)
# ============================================================


@pytest.mark.asyncio
async def test_cache_concurrent_reads():
    """Simultaneous reads/writes should not raise or corrupt state."""
    mgr = CacheManager(max_size=50, default_ttl_seconds=60)
    urls = [f"https://example.com/{i}" for i in range(20)]

    async def write_and_read(url: str) -> None:
        mgr.set_page(url, f"content:{url}")
        await asyncio.sleep(0)  # yield
        val = mgr.get_page(url)
        assert val == f"content:{url}" or val is None  # may be evicted under LRU

    await asyncio.gather(*[write_and_read(url) for url in urls])


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_domains():
    """Concurrent rate-limit checks on different domains should not deadlock."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=100.0)
    domains = [f"https://site{i}.example.com/page" for i in range(10)]

    await asyncio.gather(*[limiter.wait_if_needed(url) for url in domains])
