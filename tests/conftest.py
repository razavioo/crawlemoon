"""Pytest configuration and fixtures."""

import pytest
import tempfile
import shutil
import os
from typing import AsyncGenerator

from src.core.browser.pool import BrowserPool
from src.core.cache.manager import CacheManager
from src.core.session.manager import SessionManager


# Configure pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (may require network)"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance benchmark"
    )



@pytest.fixture
async def browser_pool() -> AsyncGenerator[BrowserPool, None]:
    """Create a browser pool for testing."""
    pool = BrowserPool(max_size=2, headless=True)
    await pool.initialize()
    yield pool
    await pool.close()


@pytest.fixture
def cache_manager() -> CacheManager:
    """Create a cache manager for testing."""
    return CacheManager(max_size=100, default_ttl_seconds=60)


@pytest.fixture
async def session_manager() -> AsyncGenerator[SessionManager, None]:
    """Create a session manager for testing."""
    manager = SessionManager(storage_path=".test_sessions")
    yield manager
    # Cleanup
    if os.path.exists(".test_sessions"):
        shutil.rmtree(".test_sessions")


@pytest.fixture
def proxy_pool():
    """Create a proxy pool for testing."""
    from src.core.browser.proxy_pool import ProxyPool, RotationStrategy
    
    pool = ProxyPool(
        proxies=["http://proxy1:8080", "http://proxy2:8080"],
        rotation_strategy=RotationStrategy.ROUND_ROBIN
    )
    return pool


@pytest.fixture
def rate_limiter():
    """Create a rate limiter for testing."""
    from src.core.rate_limiter import RateLimiter
    
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=10.0)
    return limiter


@pytest.fixture
def content_extractor():
    """Create a content extractor for testing."""
    from src.intelligence.extraction.content import ContentExtractor
    
    return ContentExtractor()


@pytest.fixture
def smart_extractor():
    """Create a smart extractor for testing."""
    from src.intelligence.extraction.smart import SmartExtractor
    
    return SmartExtractor()


@pytest.fixture
def technology_detector():
    """Create a technology detector for testing."""
    from src.intelligence.security.technology_detector import TechnologyDetector
    
    return TechnologyDetector()


@pytest.fixture
def sitemap_analyzer():
    """Create a sitemap analyzer for testing."""
    from src.intelligence.network.sitemap import SitemapAnalyzer
    
    return SitemapAnalyzer()


@pytest.fixture
def js_analyzer():
    """Create a JS analyzer for testing."""
    from src.intelligence.js.analyzer import JSAnalyzer
    
    return JSAnalyzer()


@pytest.fixture
def js_deobfuscator():
    """Create a JS deobfuscator for testing."""
    from src.intelligence.js.deobfuscator import JSDeobfuscator
    
    return JSDeobfuscator()


@pytest.fixture
def bot_detector():
    """Create a bot detection analyzer for testing."""
    from src.intelligence.security.bot_detection import BotDetectionAnalyzer
    
    return BotDetectionAnalyzer()


@pytest.fixture
def api_discovery():
    """Create an API discovery engine for testing."""
    from src.intelligence.network.api_discovery import APIDiscoveryEngine
    
    return APIDiscoveryEngine()


@pytest.fixture
def network_interceptor():
    """Create a network interceptor for testing."""
    from src.intelligence.network.interceptor import DeepNetworkInterceptor
    
    return DeepNetworkInterceptor()


@pytest.fixture
def crawler_generator():
    """Create a crawler generator for testing."""
    from src.intelligence.generator.crawler_gen import CrawlerGenerator
    
    return CrawlerGenerator()


@pytest.fixture
def recording_storage():
    """Create a recording storage for testing."""
    from src.core.recording_storage import RecordingStorage
    
    tmpdir = tempfile.mkdtemp()
    storage = RecordingStorage(storage_dir=tmpdir)
    yield storage
    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mcp_config():
    """Create MCP server config for testing."""
    from src.mcp.config import MCPServerConfig
    
    return MCPServerConfig(
        navigation_timeout=10.0,
        request_timeout=10.0,
        operation_timeout=30.0,
        headless=True,
        max_browser_pool_size=2,
    )



