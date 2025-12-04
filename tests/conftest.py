"""Pytest configuration and fixtures."""

import pytest
import asyncio
from typing import AsyncGenerator

from src.core.browser.pool import BrowserPool
from src.core.cache.manager import CacheManager
from src.core.session.manager import SessionManager


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


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
    import os
    import shutil
    if os.path.exists(".test_sessions"):
        shutil.rmtree(".test_sessions")



