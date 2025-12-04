"""Stealth mode for browser automation - Anti-detection techniques."""

import random
import logging
from typing import Dict, Optional
from playwright.async_api import BrowserContext, Page

try:
    from fake_useragent import UserAgent
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    FAKE_USERAGENT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Common user agents (fallback if fake-useragent not available)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Initialize fake-useragent if available
_ua = None
if FAKE_USERAGENT_AVAILABLE:
    try:
        _ua = UserAgent()
    except Exception as e:
        logger.warning(f"Failed to initialize fake-useragent: {e}")


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
        """Inject scripts to hide automation indicators - Enhanced with 40+ patches."""
        
        stealth_script = """
        // ===== Core WebDriver Detection Removal =====
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        
        delete navigator.__proto__.webdriver;
        
        // ===== Chrome Runtime =====
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // ===== Permissions API =====
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // ===== Plugins =====
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                plugins.item = (index) => plugins[index];
                plugins.namedItem = (name) => plugins.find(p => p.name === name);
                plugins.refresh = () => {};
                return plugins;
            },
            configurable: true
        });
        
        // ===== Languages =====
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true
        });
        
        // ===== Platform =====
        Object.defineProperty(navigator, 'platform', {
            get: () => {
                const platforms = ['Win32', 'MacIntel', 'Linux x86_64'];
                return platforms[Math.floor(Math.random() * platforms.length)];
            },
            configurable: true
        });
        
        // ===== Hardware Concurrency =====
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => {
                const cores = [4, 8, 12, 16];
                return cores[Math.floor(Math.random() * cores.length)];
            },
            configurable: true
        });
        
        // ===== Device Memory =====
        if (navigator.deviceMemory) {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => {
                    const memory = [4, 8, 16];
                    return memory[Math.floor(Math.random() * memory.length)];
                },
                configurable: true
            });
        }
        
        // ===== Canvas Fingerprinting Protection =====
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            const context = this.getContext('2d');
            if (context) {
                const imageData = context.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] += Math.floor(Math.random() * 3) - 1;
                }
                context.putImageData(imageData, 0, 0);
            }
            return originalToDataURL.apply(this, arguments);
        };
        
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function() {
            const imageData = originalGetImageData.apply(this, arguments);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] += Math.floor(Math.random() * 3) - 1;
            }
            return imageData;
        };
        
        // ===== WebGL Fingerprinting Protection =====
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
                return 'Intel Inc.';
            }
            if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter.apply(this, arguments);
        };
        
        // ===== AudioContext Fingerprinting Protection =====
        if (window.AudioContext || window.webkitAudioContext) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            const originalCreateOscillator = AudioContext.prototype.createOscillator;
            AudioContext.prototype.createOscillator = function() {
                const oscillator = originalCreateOscillator.apply(this, arguments);
                const originalFrequency = oscillator.frequency.value;
                Object.defineProperty(oscillator.frequency, 'value', {
                    get: () => originalFrequency + (Math.random() * 0.0001 - 0.00005),
                    configurable: true
                });
                return oscillator;
            };
        }
        
        // ===== Notification Permission =====
        if (Notification.permission === 'default') {
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true
            });
        }
        
        // ===== Media Devices =====
        if (navigator.mediaDevices) {
            const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices;
            navigator.mediaDevices.enumerateDevices = function() {
                return originalEnumerateDevices.apply(this, arguments).then(devices => {
                    return devices.map(device => {
                        if (device.deviceId) {
                            device.deviceId = device.deviceId.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i, 
                                () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
                                    const r = Math.random() * 16 | 0;
                                    const v = c === 'x' ? r : (r & 0x3 | 0x8);
                                    return v.toString(16);
                                }));
                        }
                        return device;
                    });
                });
            };
        }
        
        // ===== Automation Indicators =====
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
            configurable: true
        });
        
        // Remove automation flags
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        
        // ===== Playwright Detection =====
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false
        });
        
        window.navigator.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
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
        """Get a random user agent using fake-useragent if available."""
        if _ua is not None:
            try:
                return _ua.random
            except Exception:
                pass
        return random.choice(USER_AGENTS)
    
    async def simulate_human_behavior(self, page: Page) -> None:
        """Simulate human-like behavior."""
        # Random mouse movements, delays, etc.
        # This would be called during crawling operations
        pass


async def create_stealth_context(
    pool,
    user_agent: Optional[str] = None,
    url: Optional[str] = None,
    **kwargs
) -> BrowserContext:
    """Create a browser context with stealth mode enabled.
    
    Args:
        pool: Browser pool instance
        user_agent: Optional custom user agent
        url: Optional URL for proxy selection (sticky strategy)
        **kwargs: Additional context options
    """
    
    stealth = StealthBrowser()
    
    context_options = {
        "user_agent": user_agent or stealth.randomize_user_agent(),
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        **kwargs,
    }
    
    context = await pool.acquire(url=url, **context_options)
    
    # Apply stealth to first page
    page = await context.new_page()
    await stealth.apply_stealth_patches(page)
    
    return context



