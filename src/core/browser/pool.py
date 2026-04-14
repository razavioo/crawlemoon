"""Browser Pool Manager with context isolation and auto-restart."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
    Playwright,
    Error as PlaywrightError,
)

from .proxy_pool import ProxyPool, RotationStrategy
from ...exceptions import BrowserInitError, BrowserPoolExhaustedError, BrowserPoolError

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
        proxy_pool: Optional[ProxyPool] = None,
    ):
        self.max_size = max_size
        self.max_age_minutes = max_age_minutes
        self.headless = headless
        self.browser_type = browser_type
        self.proxy_pool = proxy_pool
        
        self._playwright: Optional[Playwright] = None
        self._instances: List[BrowserInstance] = []
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize Playwright and browser pool."""
        try:
            self._playwright = await async_playwright().start()
            logger.info("Browser pool initialized")
        except Exception as exc:
            raise BrowserInitError(f"Failed to start Playwright: {exc}") from exc

    async def warmup(self, count: int = 1) -> None:
        """Pre-create *count* browser instances so the first real request is fast.

        Args:
            count: Number of instances to create eagerly (capped at max_size).
        """
        count = min(count, self.max_size)
        logger.info("Browser pool warmup: creating %d instance(s)", count)
        tasks = [self._create_new_instance() for _ in range(count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("Warmup instance %d failed: %s", i, result)
    
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
    
    async def acquire(self, url: Optional[str] = None, **context_options) -> BrowserContext:
        """Acquire a browser context from the pool.
        
        Args:
            url: Optional URL to extract domain for sticky proxy strategy
            **context_options: Additional context options
        """
        async with self._lock:
            # Clean up expired or overused instances
            await self._cleanup()
            
            # Get proxy if proxy pool is configured
            proxy_config = None
            if self.proxy_pool:
                domain = None
                if url:
                    parsed = urlparse(url)
                    domain = parsed.netloc
                
                proxy = await self.proxy_pool.get_proxy(domain=domain)
                if proxy:
                    proxy_config = proxy.to_playwright_config()
                    context_options["proxy"] = proxy_config
                    logger.debug(f"Using proxy: {proxy.url} for {url or 'context'}")
            
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
            
        # Pool is full — wait iteratively instead of recursing
        logger.warning("Browser pool is full, waiting for a slot...")
        deadline = time.monotonic() + 30
        while True:
            await asyncio.sleep(1)
            async with self._lock:
                for instance in self._instances:
                    if not instance.is_expired() and not instance.is_overused():
                        instance.last_used = datetime.now()
                        instance.usage_count += 1
                        return instance.context
                if len(self._instances) < self.max_size:
                    return await self._create_new_instance(**context_options)
            if time.monotonic() > deadline:
                raise BrowserPoolExhaustedError("Browser pool exhausted: no slot available after 30s")
    
    async def _create_new_instance(self, **context_options) -> BrowserContext:
        """Create a new browser instance."""
        if not self._playwright:
            await self.initialize()

        try:
            browser = await getattr(self._playwright, self.browser_type).launch(
                headless=self.headless
            )
        except PlaywrightError as exc:
            raise BrowserInitError(f"Failed to launch {self.browser_type}: {exc}") from exc

        try:
            context = await browser.new_context(**context_options)
        except PlaywrightError as exc:
            await browser.close()
            raise BrowserPoolError(f"Failed to create browser context: {exc}") from exc
        
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
            except PlaywrightError as exc:
                logger.warning("Error closing browser context during cleanup: %s", exc)
            try:
                await instance.browser.close()
            except PlaywrightError as exc:
                logger.warning("Error closing browser during cleanup: %s", exc)
            try:
                self._instances.remove(instance)
                logger.info("Removed browser instance (pool size: %d)", len(self._instances))
            except ValueError:
                pass  # Already removed by a concurrent cleanup
    
    async def release(self, context: BrowserContext) -> None:
        """Release a context back to the pool."""
        # Context is kept in pool for reuse
        # Actual cleanup happens in _cleanup()
        pass
    
    def get_stats(self) -> Dict:
        """Get pool statistics."""
        stats = {
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
        
        if self.proxy_pool:
            stats["proxy_pool"] = self.proxy_pool.get_stats()
        
        return stats
    
    def set_proxy_pool(self, proxy_pool: Optional[ProxyPool]) -> None:
        """Set or update the proxy pool."""
        self.proxy_pool = proxy_pool
        logger.info("Proxy pool updated")



