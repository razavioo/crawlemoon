"""Stealth mode for browser automation - Anti-detection techniques."""

import random
import logging
from typing import Dict, Optional
from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)

# Common user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class StealthBrowser:
    """Apply stealth techniques to browser instances."""
    
    def __init__(self):
        self.applied_stealth = False
    
    async def apply_stealth_patches(self, page: Page) -> None:
        """Apply all stealth patches to a page."""
        if self.applied_stealth:
            return
        
        await self._inject_stealth_scripts(page)
        await self._override_properties(page)
        await self._randomize_fingerprint(page)
        
        self.applied_stealth = True
        logger.info("Stealth patches applied")
    
    async def _inject_stealth_scripts(self, page: Page) -> None:
        """Inject scripts to hide automation indicators."""
        
        stealth_script = """
        // Hide webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Mock plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // Mock languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Override chrome runtime
        window.chrome = {
            runtime: {}
        };
        
        // Hide automation
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false
        });
        """
        
        await page.add_init_script(stealth_script)
    
    async def _override_properties(self, page: Page) -> None:
        """Override properties that reveal automation."""
        
        overrides = """
        // Override getBattery
        if (navigator.getBattery) {
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1
            });
        }
        
        // Override connection
        if (navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10
                })
            });
        }
        """
        
        await page.add_init_script(overrides)
    
    async def _randomize_fingerprint(self, page: Page) -> None:
        """Randomize browser fingerprint."""
        
        # Random viewport size
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
        ]
        
        viewport = random.choice(viewports)
        await page.set_viewport_size(viewport)
        
        logger.debug(f"Randomized viewport: {viewport}")
    
    def randomize_user_agent(self) -> str:
        """Get a random user agent."""
        return random.choice(USER_AGENTS)
    
    async def simulate_human_behavior(self, page: Page) -> None:
        """Simulate human-like behavior."""
        # Random mouse movements, delays, etc.
        # This would be called during crawling operations
        pass


async def create_stealth_context(
    pool,
    user_agent: Optional[str] = None,
    **kwargs
) -> BrowserContext:
    """Create a browser context with stealth mode enabled."""
    
    stealth = StealthBrowser()
    
    context_options = {
        "user_agent": user_agent or stealth.randomize_user_agent(),
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        **kwargs,
    }
    
    context = await pool.acquire(**context_options)
    
    # Apply stealth to first page
    page = await context.new_page()
    await stealth.apply_stealth_patches(page)
    
    return context


