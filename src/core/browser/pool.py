"""Browser Pool Manager with context isolation and auto-restart."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
    Playwright,
)

logger = logging.getLogger(__name__)


@dataclass
class BrowserInstance:
    """Represents a single browser instance in the pool."""
    
    browser: Browser
    context: BrowserContext
    created_at: datetime
    last_used: datetime
    usage_count: int = 0
    max_usage: int = 100
    
    def is_expired(self, max_age_minutes: int = 60) -> bool:
        """Check if browser instance is too old."""
        age = datetime.now() - self.created_at
        return age > timedelta(minutes=max_age_minutes)
    
    def is_overused(self) -> bool:
        """Check if browser instance has exceeded usage limit."""
        return self.usage_count >= self.max_usage


class BrowserPool:
    """Manages a pool of browser instances with automatic cleanup."""
    
    def __init__(
        self,
        max_size: int = 5,
        max_age_minutes: int = 60,
        headless: bool = True,
        browser_type: str = "chromium",
    ):
        self.max_size = max_size
        self.max_age_minutes = max_age_minutes
        self.headless = headless
        self.browser_type = browser_type
        
        self._playwright: Optional[Playwright] = None
        self._instances: List[BrowserInstance] = []
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize Playwright and browser pool."""
        self._playwright = await async_playwright().start()
        logger.info("Browser pool initialized")
    
    async def close(self) -> None:
        """Close all browser instances and Playwright."""
        async with self._lock:
            for instance in self._instances:
                try:
                    await instance.context.close()
                    await instance.browser.close()
                except Exception as e:
                    logger.error(f"Error closing browser instance: {e}")
            
            self._instances.clear()
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            
            logger.info("Browser pool closed")
    
    async def acquire(self, **context_options) -> BrowserContext:
        """Acquire a browser context from the pool."""
        async with self._lock:
            # Clean up expired or overused instances
            await self._cleanup()
            
            # Try to reuse existing instance
            for instance in self._instances:
                if not instance.is_expired() and not instance.is_overused():
                    instance.last_used = datetime.now()
                    instance.usage_count += 1
                    logger.debug(f"Reusing browser instance (usage: {instance.usage_count})")
                    return instance.context
            
            # Create new instance if pool not full
            if len(self._instances) < self.max_size:
                return await self._create_new_instance(**context_options)
            
            # Wait and retry if pool is full
            logger.warning("Browser pool is full, waiting...")
            await asyncio.sleep(1)
            return await self.acquire(**context_options)
    
    async def _create_new_instance(self, **context_options) -> BrowserContext:
        """Create a new browser instance."""
        if not self._playwright:
            await self.initialize()
        
        browser = await getattr(self._playwright, self.browser_type).launch(
            headless=self.headless
        )
        
        context = await browser.new_context(**context_options)
        
        instance = BrowserInstance(
            browser=browser,
            context=context,
            created_at=datetime.now(),
            last_used=datetime.now(),
            usage_count=1,
        )
        
        self._instances.append(instance)
        logger.info(f"Created new browser instance (pool size: {len(self._instances)})")
        
        return context
    
    async def _cleanup(self) -> None:
        """Remove expired or overused instances."""
        to_remove = []
        
        for instance in self._instances:
            if instance.is_expired() or instance.is_overused():
                to_remove.append(instance)
        
        for instance in to_remove:
            try:
                await instance.context.close()
                await instance.browser.close()
                self._instances.remove(instance)
                logger.info(f"Removed browser instance (pool size: {len(self._instances)})")
            except Exception as e:
                logger.error(f"Error removing browser instance: {e}")
    
    async def release(self, context: BrowserContext) -> None:
        """Release a context back to the pool."""
        # Context is kept in pool for reuse
        # Actual cleanup happens in _cleanup()
        pass
    
    def get_stats(self) -> Dict:
        """Get pool statistics."""
        return {
            "size": len(self._instances),
            "max_size": self.max_size,
            "instances": [
                {
                    "usage_count": inst.usage_count,
                    "age_minutes": (datetime.now() - inst.created_at).total_seconds() / 60,
                    "last_used_minutes": (datetime.now() - inst.last_used).total_seconds() / 60,
                }
                for inst in self._instances
            ],
        }



