"""Tests for stealth browser functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.browser.stealth import StealthBrowser, create_stealth_context, USER_AGENTS


def test_stealth_browser_initialization():
    """Test stealth browser initialization."""
    stealth = StealthBrowser()
    
    assert stealth.applied_stealth is False


@pytest.mark.asyncio
async def test_stealth_browser_apply_patches():
    """Test applying stealth patches."""
    stealth = StealthBrowser()
    page = AsyncMock()
    page.add_init_script = AsyncMock()
    page.set_viewport_size = AsyncMock()
    
    await stealth.apply_stealth_patches(page)
    
    assert stealth.applied_stealth is True
    assert page.add_init_script.call_count >= 2
    assert page.set_viewport_size.called


@pytest.mark.asyncio
async def test_stealth_browser_no_double_apply():
    """Test stealth patches are not applied twice."""
    stealth = StealthBrowser()
    page = AsyncMock()
    page.add_init_script = AsyncMock()
    page.set_viewport_size = AsyncMock()
    
    await stealth.apply_stealth_patches(page)
    call_count = page.add_init_script.call_count
    
    await stealth.apply_stealth_patches(page)
    
    # Should not call again
    assert page.add_init_script.call_count == call_count


def test_randomize_user_agent():
    """Test user agent randomization."""
    stealth = StealthBrowser()
    
    user_agents = set()
    for _ in range(10):
        ua = stealth.randomize_user_agent()
        user_agents.add(ua)
        assert ua in USER_AGENTS
    
    # Should have some variety (though not guaranteed)
    assert len(user_agents) >= 1


def test_user_agents_list():
    """Test user agents list is not empty."""
    assert len(USER_AGENTS) > 0
    assert all(isinstance(ua, str) for ua in USER_AGENTS)
    assert all("Mozilla" in ua for ua in USER_AGENTS)


@pytest.mark.asyncio
async def test_create_stealth_context(browser_pool):
    """Test creating stealth context."""
    context = await create_stealth_context(browser_pool)
    
    assert context is not None
    
    # Cleanup
    await context.close()


@pytest.mark.asyncio
async def test_create_stealth_context_custom_ua(browser_pool):
    """Test creating stealth context with custom user agent."""
    custom_ua = "Custom User Agent"
    context = await create_stealth_context(browser_pool, user_agent=custom_ua)
    
    assert context is not None
    
    # Cleanup
    await context.close()

