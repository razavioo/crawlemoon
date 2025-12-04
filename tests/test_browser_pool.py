"""Tests for browser pool management."""

import pytest
import asyncio
from datetime import datetime, timedelta

from src.core.browser.pool import BrowserPool, BrowserInstance
from playwright.async_api import BrowserContext


@pytest.mark.asyncio
async def test_browser_pool_initialization(browser_pool):
    """Test browser pool initialization."""
    assert browser_pool._playwright is not None
    assert browser_pool.max_size == 2
    assert len(browser_pool._instances) == 0


@pytest.mark.asyncio
async def test_browser_pool_acquire(browser_pool):
    """Test acquiring browser context from pool."""
    context = await browser_pool.acquire()
    assert context is not None
    assert isinstance(context, BrowserContext)
    assert len(browser_pool._instances) == 1


@pytest.mark.asyncio
async def test_browser_pool_reuse(browser_pool):
    """Test reusing browser instances."""
    context1 = await browser_pool.acquire()
    context2 = await browser_pool.acquire()
    
    # Both should use the same instance if available
    stats = browser_pool.get_stats()
    assert stats["size"] <= 2


@pytest.mark.asyncio
async def test_browser_pool_max_size(browser_pool):
    """Test browser pool respects max size."""
    contexts = []
    for _ in range(3):
        context = await browser_pool.acquire()
        contexts.append(context)
    
    stats = browser_pool.get_stats()
    assert stats["size"] <= browser_pool.max_size


@pytest.mark.asyncio
async def test_browser_pool_stats(browser_pool):
    """Test browser pool statistics."""
    await browser_pool.acquire()
    stats = browser_pool.get_stats()
    
    assert "size" in stats
    assert "max_size" in stats
    assert "instances" in stats
    assert stats["size"] > 0


@pytest.mark.asyncio
async def test_browser_instance_expiration():
    """Test browser instance expiration check."""
    from playwright.async_api import async_playwright
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    
    # Create instance with old timestamp
    instance = BrowserInstance(
        browser=browser,
        context=context,
        created_at=datetime.now() - timedelta(minutes=61),
        last_used=datetime.now(),
    )
    
    assert instance.is_expired(max_age_minutes=60) is True
    
    await context.close()
    await browser.close()
    await playwright.stop()


@pytest.mark.asyncio
async def test_browser_instance_overuse():
    """Test browser instance overuse detection."""
    from playwright.async_api import async_playwright
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    
    instance = BrowserInstance(
        browser=browser,
        context=context,
        created_at=datetime.now(),
        last_used=datetime.now(),
        usage_count=100,
        max_usage=100,
    )
    
    assert instance.is_overused() is True
    
    await context.close()
    await browser.close()
    await playwright.stop()


@pytest.mark.asyncio
async def test_browser_pool_cleanup(browser_pool):
    """Test browser pool cleanup of expired instances."""
    # Create an expired instance manually (for testing)
    from playwright.async_api import async_playwright
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    
    expired_instance = BrowserInstance(
        browser=browser,
        context=context,
        created_at=datetime.now() - timedelta(minutes=61),
        last_used=datetime.now() - timedelta(minutes=61),
    )
    
    browser_pool._instances.append(expired_instance)
    
    # Acquire should trigger cleanup
    await browser_pool.acquire()
    
    # Expired instance should be removed
    assert expired_instance not in browser_pool._instances
    
    await playwright.stop()


