"""MCP Server implementation for Crawlemoon - Enhanced and Production-Ready."""

import asyncio
import logging
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.types import Tool, TextContent

from ..core.browser.pool import BrowserPool
from ..core.browser.stealth import create_stealth_context, apply_stealth_to_page
from ..core.browser.proxy_pool import ProxyPool, RotationStrategy, parse_proxy_source
from ..core.http.proxy import set_http_proxy_pool
from ..core.browser.xray import CrawlemoonV2rayManager
from ..core.browser.cdp import CDPClient
from ..core.rate_limiter import RateLimiter
from ..core.recording_storage import RecordingStorage
from ..core.session.manager import SessionManager
from ..core.cache.manager import CacheManager
from ..intelligence.network.interceptor import DeepNetworkInterceptor
from ..intelligence.network.api_discovery import APIDiscoveryEngine
from ..intelligence.network.analyzer import RequestAnalyzer
try:
    from ..intelligence.network.sitemap import SitemapAnalyzer
except ImportError as _sitemap_import_error:
    SitemapAnalyzer = None
    logging.getLogger(__name__).warning(
        "SitemapAnalyzer unavailable; analyze_sitemap will be disabled: %s",
        _sitemap_import_error,
    )
from ..intelligence.js.analyzer import JSAnalyzer
from ..intelligence.js.deobfuscator import JSDeobfuscator
from ..intelligence.recorder.session import SessionRecorder
from ..intelligence.security.bot_detection import BotDetectionAnalyzer
from ..intelligence.security.technology_detector import get_technology_detector
from ..intelligence.extraction.content import get_content_extractor
from ..intelligence.extraction.smart import get_smart_extractor
from ..intelligence.generator.crawler_gen import CrawlerGenerator
from .config import MCPServerConfig
from .utils import validate_arguments, with_retry, validate_js_payload
from .schemas import PYDANTIC_AVAILABLE
from ..exceptions import (
    RecordingNotFoundError,
    RecordingExpiredError,
    ValidationError,
)
from playwright.async_api import Error as PlaywrightError

logger = logging.getLogger(__name__)

# Global configuration
config = MCPServerConfig.from_env()

# Initialize proxy pool if configured
_proxy_pool = None
try:
    proxy_entries = parse_proxy_source(config.proxies, proxies_file=config.proxies_file)
    if proxy_entries:
        try:
            strategy = RotationStrategy(config.proxy_rotation.lower())
        except ValueError:
            strategy = RotationStrategy.ROUND_ROBIN

        _proxy_pool = ProxyPool(
            rotation_strategy=strategy,
            health_check_interval=config.proxy_health_check_interval,
            fail_closed=config.proxy_fail_closed,
        )
        for proxy_entry in proxy_entries:
            _proxy_pool.add_proxy(proxy_entry, default_scheme=config.proxy_default_scheme)
        set_http_proxy_pool(_proxy_pool)
        logger.info("Initialized proxy pool with %d proxies", len(_proxy_pool.proxies))
except Exception as proxy_init_error:
    if config.proxy_fail_closed:
        raise
    logger.error("Failed to initialize proxy pool: %s", proxy_init_error, exc_info=True)

# Initialize global instances
browser_pool = BrowserPool(
    max_size=config.max_browser_pool_size,
    headless=config.headless,
    browser_type=config.browser_type,
    proxy_pool=_proxy_pool,
)
# Initialize dynamic Xray/V2ray manager
_xray_manager = None

network_interceptor = DeepNetworkInterceptor()
api_discovery = APIDiscoveryEngine()
request_analyzer = RequestAnalyzer()
sitemap_analyzer = SitemapAnalyzer() if SitemapAnalyzer else None
js_analyzer = JSAnalyzer()
js_deobfuscator = JSDeobfuscator()
bot_detector = BotDetectionAnalyzer()
content_extractor = get_content_extractor()
# Smart extractor uses config for LLM settings (supports OpenRouter, Groq, Ollama, etc.)
smart_extractor = get_smart_extractor(
    api_key=config.llm_api_key,
    model=config.llm_model,
    base_url=config.llm_base_url,
    provider=config.llm_provider,
)
technology_detector = get_technology_detector()
recording_storage = RecordingStorage(storage_dir=config.recording_storage_dir)
rate_limiter = RateLimiter()
cache_manager = CacheManager(max_size=1000, default_ttl_seconds=3600)

# Configure rate limiter from environment
default_rps = float(os.getenv("CRAWLEMOON_RATE_LIMIT_RPS", "1.0"))
rate_limiter.set_default_rate_limit(requests_per_second=default_rps)

# Initialize session manager
session_storage_dir = os.getenv("CRAWLEMOON_SESSION_DIR")
user_data_dir = os.getenv("CRAWLEMOON_USER_DATA_DIR")
session_manager = SessionManager(
    storage_path=session_storage_dir,
    user_data_dir=user_data_dir,
)

# Active recordings tracking
_active_recordings: Dict[str, Tuple[SessionRecorder, Any, Any]] = {}  # recording_id -> (recorder, page, context)

# Initialize browser pool
async def init_browser_pool():
    """Initialize browser pool."""
    await browser_pool.initialize()
    logger.info("Browser pool initialized")

# MCP Server
server = Server("crawlemoon-mcp-server")


@asynccontextmanager
async def browser_context_manager(url: Optional[str] = None):
    """Context manager for browser operations with proper cleanup.
    
    Args:
        url: Optional URL for proxy selection (sticky strategy)
    
    Note: Only closes the page, not the context. The browser pool manages
    context lifecycle to enable reuse across requests.
    """
    context = None
    page = None
    try:
        context = await create_stealth_context(browser_pool, url=url)
        page = await context.new_page()
        page.set_default_timeout(config.navigation_timeout * 1000)  # Playwright uses milliseconds
        
        # Apply stealth patches to the page
        await apply_stealth_to_page(context, page)
        
        yield page
    finally:
        if page:
            try:
                await page.close()
            except (PlaywrightError, AttributeError) as e:
                logger.warning("Error closing page: %s", e)
        # Don't close the context - let the browser pool manage its lifecycle
        # This allows context reuse and prevents "Target closed" errors


async def navigate_to_url(page, url: str):
    """Navigate a page to a URL, recording the response in the rate limiter."""
    wait_until = "networkidle" if config.wait_for_network_idle else "load"
    response = await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
    if response:
        rate_limiter.record_response(url, response.status)
    return response


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="deep_analyze",
            description="Perform comprehensive deep analysis of a website including network traffic, JavaScript analysis, and security detection. Returns detailed insights about APIs, protection mechanisms, and fingerprinting techniques.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the website to analyze (must be a valid HTTP/HTTPS URL)"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["basic", "full"],
                        "description": "Analysis depth: 'basic' for quick analysis, 'full' for comprehensive analysis",
                        "default": "full"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="discover_apis",
            description="Discover all REST and GraphQL APIs on a website, including hidden and undocumented endpoints. Useful for API reverse engineering and documentation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Website URL to analyze for API endpoints"
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "Include hidden/internal APIs that may not be publicly documented",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="introspect_graphql",
            description="Extract complete GraphQL schema from an endpoint using introspection. Returns schema, queries, mutations, and subscriptions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "GraphQL endpoint URL (e.g., https://api.example.com/graphql)"
                    }
                },
                "required": ["endpoint"]
            }
        ),
        Tool(
            name="analyze_websocket",
            description="Intercept and analyze WebSocket connections on a page. Captures messages, connection details, and message patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Page URL that establishes WebSocket connections"
                    },
                    "wait_time": {
                        "type": "number",
                        "description": "Time in seconds to wait for WebSocket connections (default: 5)",
                        "default": 5
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="record_session",
            description="Start recording an interactive browser session. Records all user interactions, network requests, and page state changes. Use stop_recording to finish.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Starting URL for the recording session"
                    },
                    "auto_save": {
                        "type": "boolean",
                        "description": "Automatically save recording when stopped (default: true)",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="stop_recording",
            description="Stop an active recording session and optionally save it. Returns recording ID and statistics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "ID of the recording to stop"
                    },
                    "save": {
                        "type": "boolean",
                        "description": "Save recording to storage (default: true)",
                        "default": True
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="list_recordings",
            description="List all available recordings (both active and saved). Returns metadata about each recording.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "saved"],
                        "description": "Filter by recording status (default: all)",
                        "default": "all"
                    }
                }
            }
        ),
        Tool(
            name="get_recording_status",
            description="Get status and details of a specific recording session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "ID of the recording to check"
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="generate_crawler",
            description="Generate a crawler script from a recorded session. Supports multiple output formats including YAML, Python, and Playwright.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "Recording ID or file path to the recording JSON file"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["yaml", "python", "playwright"],
                        "description": "Output format for the generated crawler",
                        "default": "yaml"
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="analyze_auth",
            description="Analyze authentication flow on a login page. Identifies auth mechanisms, token handling, and authentication endpoints.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Login page URL to analyze"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="detect_protection",
            description="Detect anti-bot systems, CAPTCHAs, and fingerprinting techniques used on a website.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Website URL to analyze for protection mechanisms"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="deobfuscate_js",
            description="Deobfuscate JavaScript code. Detects obfuscation techniques and attempts to restore readable code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Obfuscated JavaScript code to deobfuscate"
                    }
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="extract_from_js",
            description="Extract API endpoints, URLs, constants, and authentication logic from JavaScript code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to analyze"
                    }
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="health_check",
            description="Check the health status of the MCP server, browser pool, and storage systems.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="configure_proxies",
            description="Configure proxy pool with flexible inputs, rotation strategies, and health checks. Supports URL and host:port:user:pass formats over HTTP, HTTPS, SOCKS4, and SOCKS5.",
            inputSchema={
                "type": "object",
                "properties": {
                    "proxies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of proxy URLs or host:port[:username:password] entries"
                    },
                    "proxies_text": {
                        "type": "string",
                        "description": "Newline or comma separated proxy entries"
                    },
                    "proxies_file": {
                        "type": "string",
                        "description": "Local file path containing one proxy per line"
                    },
                    "username": {
                        "type": "string",
                        "description": "Default username for host:port entries"
                    },
                    "password": {
                        "type": "string",
                        "description": "Default password for host:port entries"
                    },
                    "default_scheme": {
                        "type": "string",
                        "enum": ["http", "https", "socks4", "socks5"],
                        "description": "Scheme for entries without one",
                        "default": "http"
                    },
                    "rotation_strategy": {
                        "type": "string",
                        "enum": ["round_robin", "random", "sticky", "least_used"],
                        "description": "Proxy rotation strategy (default: round_robin)",
                        "default": "round_robin"
                    },
                    "health_check_interval": {
                        "type": "number",
                        "description": "Health check interval in seconds (default: 300)",
                        "default": 300
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Replace existing proxy pool instead of merging",
                        "default": True
                    },
                    "fail_closed": {
                        "type": "boolean",
                        "description": "Return an error instead of falling back when proxy setup fails",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="save_session",
            description="Save a browser session (cookies, localStorage, sessionStorage) for later reuse. Provide a URL to capture live browser state from that page, or omit to persist an already-created session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to save"
                    },
                    "url": {
                        "type": "string",
                        "description": "Optional URL to navigate to and capture live cookies/storage from"
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="load_session",
            description="Load a previously saved session and apply it to a browser context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to load"
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="list_sessions",
            description="List all saved sessions with metadata.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="analyze_sitemap",
            description="Analyze sitemap.xml file to extract all URLs and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sitemap_url": {
                        "type": "string",
                        "description": "URL of the sitemap.xml file"
                    }
                },
                "required": ["sitemap_url"]
            }
        ),
        Tool(
            name="check_robots",
            description="Analyze robots.txt file to check crawl rules and discover sitemaps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Base URL of the website (robots.txt will be fetched from root)"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="take_screenshot",
            description="Take a screenshot of a webpage. Returns base64-encoded image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to screenshot"
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page (default: false)",
                        "default": False
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "Wait for selector or 'load'/'networkidle' (optional)"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="extract_article",
            description="Extract clean article content from a webpage using intelligent content extraction. Returns title, text, markdown, and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract content from"
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "Include image references (default: true)",
                        "default": True
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["text", "markdown", "json"],
                        "description": "Output format (default: text)",
                        "default": "text"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="solve_captcha",
            description="Deprecated: detect CAPTCHA challenges and return manual-review guidance. Crawlemoon does not automate CAPTCHA solving or bypass site protections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page with CAPTCHA"
                    },
                    "captcha_type": {
                        "type": "string",
                        "enum": ["auto", "recaptcha_v2", "hcaptcha", "turnstile"],
                        "description": "CAPTCHA type to solve (default: auto)",
                        "default": "auto"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="detect_technology",
            description="Detect technology stack of a website (CMS, frameworks, CDN, analytics, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the website to analyze"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="smart_extract",
            description="Extract data from a webpage using natural language queries. Works without any paid API using pattern matching. Optionally enhanced by LLM if configured (supports OpenRouter, Groq, Ollama, and other OpenAI-compatible providers).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract from"
                    },
                    "query": {
                        "type": "string",
                        "description": "Natural language query describing what to extract (e.g., 'extract all product prices and titles')"
                    }
                },
                "required": ["url", "query"]
            }
        ),
        Tool(
            name="convert_to_markdown",
            description="Convert webpage content to clean markdown format optimized for LLM consumption.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to convert"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="stealth_request",
            description="Make an HTTP request with browser-compatible TLS behavior for authorized testing and compatibility checks. Respect site policies, robots.txt, and rate limits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to request"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                        "description": "HTTP method (default: GET)",
                        "default": "GET"
                    },
                    "browser": {
                        "type": "string",
                        "enum": ["chrome", "edge", "safari", "firefox"],
                        "description": "Browser to impersonate (default: chrome)",
                        "default": "chrome"
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional custom headers"
                    },
                    "data": {
                        "type": "object",
                        "description": "Optional request data (for POST/PUT)"
                    }
                },
                "required": ["url"]
            }
        ),
        # Cache Management Tools
        Tool(
            name="clear_cache",
            description="Clear cached pages, responses, or state snapshots. Useful for forcing fresh data retrieval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cache_type": {
                        "type": "string",
                        "enum": ["page", "response", "state", "all"],
                        "description": "Type of cache to clear (default: all)",
                        "default": "all"
                    }
                }
            }
        ),
        Tool(
            name="get_cache_stats",
            description="Get cache statistics including size, hit rates, and memory usage.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        # Rate Limiter Configuration Tools
        Tool(
            name="configure_rate_limit",
            description="Configure respectful rate limiting for specific domains or globally to reduce load and honor site limits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Domain to configure (leave empty for global/default)"
                    },
                    "requests_per_second": {
                        "type": "number",
                        "description": "Maximum requests per second (default: 1.0)",
                        "default": 1.0
                    },
                    "requests_per_minute": {
                        "type": "integer",
                        "description": "Maximum requests per minute (optional)"
                    },
                    "requests_per_hour": {
                        "type": "integer",
                        "description": "Maximum requests per hour (optional)"
                    }
                }
            }
        ),
        Tool(
            name="get_rate_limit_stats",
            description="Get current rate limiter statistics including domains in backoff and request counts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        # Proxy Management Tools
        Tool(
            name="get_proxy_stats",
            description="Get proxy pool statistics including health status, usage counts, and success rates.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="add_proxy",
            description="Add a single proxy to the pool.",
            inputSchema={
                "type": "object",
                "properties": {
                    "proxy_url": {
                        "type": "string",
                        "description": "Proxy URL or host:port[:username:password]"
                    },
                    "username": {
                        "type": "string",
                        "description": "Optional proxy username"
                    },
                    "password": {
                        "type": "string",
                        "description": "Optional proxy password"
                    },
                    "default_scheme": {
                        "type": "string",
                        "enum": ["http", "https", "socks4", "socks5"],
                        "description": "Scheme for entries without one",
                        "default": "http"
                    }
                },
                "required": ["proxy_url"]
            }
        ),
        Tool(
            name="remove_proxy",
            description="Remove a proxy from the pool.",
            inputSchema={
                "type": "object",
                "properties": {
                    "proxy_url": {
                        "type": "string",
                        "description": "Proxy URL to remove"
                    }
                },
                "required": ["proxy_url"]
            }
        ),
        Tool(
            name="test_proxy",
            description="Test a specific proxy's connectivity and health.",
            inputSchema={
                "type": "object",
                "properties": {
                    "proxy_url": {
                        "type": "string",
                        "description": "Proxy URL or host:port[:username:password] to test"
                    },
                    "test_url": {
                        "type": "string",
                        "description": "URL to use for connectivity test",
                        "default": "http://httpbin.org/ip"
                    },
                    "username": {
                        "type": "string",
                        "description": "Optional proxy username"
                    },
                    "password": {
                        "type": "string",
                        "description": "Optional proxy password"
                    },
                    "default_scheme": {
                        "type": "string",
                        "enum": ["http", "https", "socks4", "socks5"],
                        "description": "Scheme for entries without one",
                        "default": "http"
                    }
                },
                "required": ["proxy_url"]
            }
        ),
        # GraphQL Tools
        Tool(
            name="execute_graphql",
            description="Execute a GraphQL query or mutation against an endpoint.",
            inputSchema={
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "GraphQL endpoint URL"
                    },
                    "query": {
                        "type": "string",
                        "description": "GraphQL query or mutation"
                    },
                    "variables": {
                        "type": "object",
                        "description": "Optional query variables"
                    }
                },
                "required": ["endpoint", "query"]
            }
        ),
        # Page Interaction Tools
        Tool(
            name="execute_js",
            description="Execute JavaScript code on a page and return the result.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to execute JS on"
                    },
                    "script": {
                        "type": "string",
                        "description": "JavaScript code to execute"
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "Optional selector or 'load'/'networkidle' to wait for"
                    }
                },
                "required": ["url", "script"]
            }
        ),
        Tool(
            name="get_cookies",
            description="Get all cookies from a page/domain.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to get cookies from"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="get_storage",
            description="Get localStorage and sessionStorage from a page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to get storage from"
                    }
                },
                "required": ["url"]
            }
        ),
        # Recording Management Tools
        Tool(
            name="delete_recording",
            description="Delete a saved recording from storage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "ID of the recording to delete"
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="export_recording",
            description="Export a recording to various formats (JSON, HAR, Playwright test).",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "ID of the recording to export"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "har", "playwright_test"],
                        "description": "Export format (default: json)",
                        "default": "json"
                    }
                },
                "required": ["recording_id"]
            }
        ),
        # Content Extraction Tools
        Tool(
            name="extract_links",
            description="Extract all links from a webpage with optional filtering.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract links from"
                    },
                    "filter_internal": {
                        "type": "boolean",
                        "description": "Only return internal links (same domain)",
                        "default": False
                    },
                    "filter_external": {
                        "type": "boolean",
                        "description": "Only return external links (different domain)",
                        "default": False
                    },
                    "include_text": {
                        "type": "boolean",
                        "description": "Include link text in results",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="extract_forms",
            description="Extract all forms from a webpage including fields, actions, and methods.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract forms from"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="extract_metadata",
            description="Extract page metadata including Open Graph tags, Twitter cards, structured data (JSON-LD), and meta tags.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract metadata from"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="extract_tables",
            description="Extract all tables from a webpage as structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract tables from"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "csv", "markdown"],
                        "description": "Output format for tables (default: json)",
                        "default": "json"
                    }
                },
                "required": ["url"]
            }
        ),
        # CDP Tools
        Tool(
            name="execute_cdp",
            description="Execute a Chrome DevTools Protocol (CDP) command directly. For advanced browser automation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to before executing CDP command"
                    },
                    "method": {
                        "type": "string",
                        "description": "CDP method to call (e.g., 'Network.enable', 'DOM.getDocument')"
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional parameters for the CDP command"
                    }
                },
                "required": ["url", "method"]
            }
        ),
        Tool(
            name="get_dom_tree",
            description="Get the full DOM tree of a page using CDP.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Depth of DOM tree to retrieve (-1 for full tree)",
                        "default": -1
                    }
                },
                "required": ["url"]
            }
        ),
        # Performance and Analysis Tools
        Tool(
            name="measure_performance",
            description="Measure page load performance including timing metrics, resource loading, and Core Web Vitals.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to measure"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="analyze_resources",
            description="Analyze all resources loaded by a page (scripts, styles, images, fonts, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to analyze"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="check_accessibility",
            description="Run accessibility checks on a webpage and report issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to check"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="compare_pages",
            description="Compare two pages and highlight differences in structure, content, or visual appearance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url1": {
                        "type": "string",
                        "description": "First URL to compare"
                    },
                    "url2": {
                        "type": "string",
                        "description": "Second URL to compare"
                    },
                    "compare_type": {
                        "type": "string",
                        "enum": ["structure", "content", "both"],
                        "description": "Type of comparison (default: both)",
                        "default": "both"
                    }
                },
                "required": ["url1", "url2"]
            }
        ),
        Tool(
            name="monitor_network",
            description="Monitor network traffic on a page for a specified duration. Captures all requests and responses.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to monitor"
                    },
                    "duration": {
                        "type": "number",
                        "description": "Duration in seconds to monitor (default: 10)",
                        "default": 10
                    },
                    "filter_type": {
                        "type": "string",
                        "enum": ["all", "xhr", "fetch", "script", "image", "stylesheet"],
                        "description": "Filter requests by type (default: all)",
                        "default": "all"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="fill_form",
            description="Automatically fill a form on a page with provided data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page containing the form"
                    },
                    "form_selector": {
                        "type": "string",
                        "description": "CSS selector for the form (optional, uses first form if not specified)"
                    },
                    "data": {
                        "type": "object",
                        "description": "Form data as key-value pairs (field name/id -> value)"
                    },
                    "submit": {
                        "type": "boolean",
                        "description": "Submit the form after filling (default: false)",
                        "default": False
                    }
                },
                "required": ["url", "data"]
            }
        ),
        Tool(
            name="wait_and_extract",
            description="Wait for specific elements to appear on a page and extract their content. Useful for dynamic/AJAX content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page"
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to wait for and extract"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30
                    },
                    "extract_type": {
                        "type": "string",
                        "enum": ["text", "html", "attribute"],
                        "description": "What to extract (default: text)",
                        "default": "text"
                    },
                    "attribute": {
                        "type": "string",
                        "description": "Attribute name if extract_type is 'attribute'"
                    }
                },
                "required": ["url", "selector"]
            }
        ),
        Tool(
            name="crawl",
            description="Recursively crawl pages starting from a seed URL, extracting clean markdown and page metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Seed URL to start crawling from"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth to recursively follow links (default: 2, max: 5)",
                        "default": 2
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "Maximum total pages to crawl across the entire crawl session (default: 10, max: 100)",
                        "default": 10
                    },
                    "concurrency": {
                        "type": "integer",
                        "description": "Number of concurrent browser contexts/workers to run (default: 3, max: 10)",
                        "default": 3
                    },
                    "ignore_external": {
                        "type": "boolean",
                        "description": "Only follow links on the same domain (default: true)",
                        "default": True
                    },
                    "save_to_file": {
                        "type": "boolean",
                        "description": "Save crawling results to a file inside the project crawls directory (default: false)",
                        "default": False
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="structured_extract",
            description="Extract highly structured JSON data from a page directly using an LLM and a target JSON schema, bypassing brittle CSS selectors.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to extract structured data from"
                    },
                    "schema": {
                        "type": "object",
                        "description": "Target JSON schema mapping fields to types and structures"
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Optional natural-language guidance or rules for context"
                    }
                },
                "required": ["url", "schema"]
            }
        ),
        Tool(
            name="configure_xray_subscription",
            description="Configure V2ray/Xray subscription or raw links to set up automatic multi-port exit proxies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subscription_url": {
                        "type": "string",
                        "description": "URL containing base64 V2ray subscription configurations"
                    },
                    "raw_links": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of raw protocol links (vmess://, vless://, trojan://, ss://)"
                    },
                    "num_ports": {
                        "type": "integer",
                        "description": "Number of concurrent SOCKS5 ports to run (default: 3)",
                        "default": 3
                    },
                    "start_port": {
                        "type": "integer",
                        "description": "Starting port number for local SOCKS5 proxies (default: 10801)",
                        "default": 10801
                    }
                }
            }
        ),
        Tool(
            name="get_xray_status",
            description="Get the status of all active local Xray clients, exit nodes, and latencies.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="rotate_xray_node",
            description="Manually rotate the exit node on a specific local Xray port.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {
                        "type": "integer",
                        "description": "SOCKS5 port to rotate node on"
                    }
                },
                "required": ["port"]
            }
        ),
        Tool(
            name="test_xray_nodes",
            description="Concurrently measure HTTP latencies of all subscription nodes to rank the best connections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_url": {
                        "type": "string",
                        "description": "URL to check latency and connectivity against (default: http://httpbin.org/ip)",
                        "default": "http://httpbin.org/ip"
                    },
                    "max_concurrency": {
                        "type": "integer",
                        "description": "Max concurrent benchmark processes to spawn (default: 5)",
                        "default": 5
                    }
                }
            }
        ),
    ]


_tool_schema_cache: Optional[Dict[str, Any]] = None

# Map tool name -> Pydantic model class (populated lazily from schemas module)
_PYDANTIC_SCHEMA_MAP: Optional[Dict[str, Any]] = None


def _get_pydantic_schema_map() -> Dict[str, Any]:
    """Return a dict mapping tool name → Pydantic model class."""
    global _PYDANTIC_SCHEMA_MAP
    if _PYDANTIC_SCHEMA_MAP is not None:
        return _PYDANTIC_SCHEMA_MAP

    from . import schemas as _s
    _PYDANTIC_SCHEMA_MAP = {
        "deep_analyze": _s.DeepAnalyzeArgs,
        "discover_apis": _s.DiscoverAPIsArgs,
        "introspect_graphql": _s.IntrospectGraphQLArgs,
        "execute_graphql": _s.ExecuteGraphQLArgs,
        "take_screenshot": _s.TakeScreenshotArgs,
        "execute_js": _s.ExecuteJSArgs,
        "extract_article": _s.ExtractArticleArgs,
        "extract_links": _s.ExtractLinksArgs,
        "extract_forms": _s.ExtractFormsArgs,
        "extract_tables": _s.ExtractTablesArgs,
        "extract_metadata": _s.ExtractMetadataArgs,
        "convert_to_markdown": _s.ConvertToMarkdownArgs,
        "smart_extract": _s.SmartExtractArgs,
        "analyze_sitemap": _s.AnalyzeSitemapArgs,
        "check_robots": _s.CheckRobotsArgs,
        "monitor_network": _s.MonitorNetworkArgs,
        "analyze_websocket": _s.AnalyzeWebSocketArgs,
        "detect_protection": _s.DetectProtectionArgs,
        "detect_technology": _s.DetectTechnologyArgs,
        "analyze_auth": _s.AnalyzeAuthArgs,
        "check_accessibility": _s.CheckAccessibilityArgs,
        "fill_form": _s.FillFormArgs,
        "get_cookies": _s.GetCookiesArgs,
        "get_storage": _s.GetStorageArgs,
        "get_dom_tree": _s.GetDOMTreeArgs,
        "measure_performance": _s.MeasurePerformanceArgs,
        "analyze_resources": _s.AnalyzeResourcesArgs,
        "compare_pages": _s.ComparePagesArgs,
        "deobfuscate_js": _s.DeobfuscateJSArgs,
        "extract_from_js": _s.ExtractFromJSArgs,
        "solve_captcha": _s.SolveCaptchaArgs,
        "stealth_request": _s.StealthRequestArgs,
        "add_proxy": _s.AddProxyArgs,
        "remove_proxy": _s.RemoveProxyArgs,
        "test_proxy": _s.TestProxyArgs,
        "configure_proxies": _s.ConfigureProxiesArgs,
        "configure_rate_limit": _s.ConfigureRateLimitArgs,
        "save_session": _s.SaveSessionArgs,
        "load_session": _s.LoadSessionArgs,
        "record_session": _s.RecordSessionArgs,
        "stop_recording": _s.StopRecordingArgs,
        "get_recording_status": _s.GetRecordingStatusArgs,
        "delete_recording": _s.DeleteRecordingArgs,
        "export_recording": _s.ExportRecordingArgs,
        "generate_crawler": _s.GenerateCrawlerArgs,
        "execute_cdp": _s.ExecuteCDPArgs,
        "clear_cache": _s.ClearCacheArgs,
        "crawl": _s.CrawlArgs,
        "structured_extract": _s.StructuredExtractArgs,
        "configure_xray_subscription": _s.ConfigureXraySubscriptionArgs,
        "get_xray_status": _s.GetXrayStatusArgs,
        "rotate_xray_node": _s.RotateXrayNodeArgs,
        "test_xray_nodes": _s.TestXrayNodesArgs,
    }
    return _PYDANTIC_SCHEMA_MAP


async def get_tool_schema_map() -> Dict[str, Any]:
    """Return a cached map of tool name -> Tool for schema validation."""
    global _tool_schema_cache
    if _tool_schema_cache is None:
        tools = await list_tools()
        _tool_schema_cache = {t.name: t for t in tools}
    return _tool_schema_cache


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls with comprehensive error handling.

    Auth: when ``CRAWLEMOON_API_KEY`` is set in the environment, every call must
    carry a matching ``_api_key`` argument. Useful when the server is exposed
    over a non-stdio transport.
    """
    try:
        if config.api_key:
            provided = arguments.pop("_api_key", None) if isinstance(arguments, dict) else None
            if provided != config.api_key:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Unauthorized: missing or invalid _api_key"}),
                )]

        # Get tool schema for validation (cached after first call)
        tool_schema = (await get_tool_schema_map()).get(name)
        
        if not tool_schema:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
            )]
        
        # Validate arguments — prefer Pydantic model when available
        if PYDANTIC_AVAILABLE:
            schema_model = _get_pydantic_schema_map().get(name)
            if schema_model is not None:
                try:
                    schema_model(**arguments)
                except Exception as pydantic_err:
                    return [TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": f"Invalid arguments: {pydantic_err}", "tool": name},
                            ensure_ascii=False,
                        ),
                    )]
        else:
            # Fallback: JSON-schema-based validation
            required = tool_schema.inputSchema.get("required", [])
            is_valid, error_msg = validate_arguments(arguments, required, tool_schema.inputSchema)
            if not is_valid:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": error_msg}, ensure_ascii=False),
                )]

        # Route to handler
        handler_map = {
            "deep_analyze": handle_deep_analyze,
            "discover_apis": handle_discover_apis,
            "introspect_graphql": handle_introspect_graphql,
            "analyze_websocket": handle_analyze_websocket,
            "record_session": handle_record_session,
            "stop_recording": handle_stop_recording,
            "list_recordings": handle_list_recordings,
            "get_recording_status": handle_get_recording_status,
            "generate_crawler": handle_generate_crawler,
            "analyze_auth": handle_analyze_auth,
            "detect_protection": handle_detect_protection,
            "deobfuscate_js": handle_deobfuscate_js,
            "extract_from_js": handle_extract_from_js,
            "health_check": handle_health_check,
            "configure_proxies": handle_configure_proxies,
            "save_session": handle_save_session,
            "load_session": handle_load_session,
            "list_sessions": handle_list_sessions,
            "analyze_sitemap": handle_analyze_sitemap,
            "check_robots": handle_check_robots,
            "take_screenshot": handle_take_screenshot,
            "extract_article": handle_extract_article,
            "solve_captcha": handle_solve_captcha,
            "detect_technology": handle_detect_technology,
            "smart_extract": handle_smart_extract,
            "convert_to_markdown": handle_convert_to_markdown,
            "stealth_request": handle_stealth_request,
            "clear_cache": handle_clear_cache,
            "get_cache_stats": handle_get_cache_stats,
            "configure_rate_limit": handle_configure_rate_limit,
            "get_rate_limit_stats": handle_get_rate_limit_stats,
            "get_proxy_stats": handle_get_proxy_stats,
            "add_proxy": handle_add_proxy,
            "remove_proxy": handle_remove_proxy,
            "test_proxy": handle_test_proxy,
            "execute_graphql": handle_execute_graphql,
            "execute_js": handle_execute_js,
            "get_cookies": handle_get_cookies,
            "get_storage": handle_get_storage,
            "delete_recording": handle_delete_recording,
            "export_recording": handle_export_recording,
            "extract_links": handle_extract_links,
            "extract_forms": handle_extract_forms,
            "extract_metadata": handle_extract_metadata,
            "extract_tables": handle_extract_tables,
            "execute_cdp": handle_execute_cdp,
            "get_dom_tree": handle_get_dom_tree,
            "measure_performance": handle_measure_performance,
            "analyze_resources": handle_analyze_resources,
            "check_accessibility": handle_check_accessibility,
            "compare_pages": handle_compare_pages,
            "monitor_network": handle_monitor_network,
            "fill_form": handle_fill_form,
            "wait_and_extract": handle_wait_and_extract,
            "crawl": handle_crawl,
            "structured_extract": handle_structured_extract,
            "configure_xray_subscription": handle_configure_xray_subscription,
            "get_xray_status": handle_get_xray_status,
            "rotate_xray_node": handle_rotate_xray_node,
            "test_xray_nodes": handle_test_xray_nodes,
        }
        
        handler = handler_map.get(name)
        if not handler:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Handler not implemented for tool: {name}"}, ensure_ascii=False)
            )]
        
        # Execute handler with timeout
        result = await asyncio.wait_for(
            handler(arguments),
            timeout=config.operation_timeout
        )
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False, default=str)
        )]
    
    except asyncio.TimeoutError:
        logger.error(f"Tool {name} timed out after {config.operation_timeout}s")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Operation timed out after {config.operation_timeout} seconds",
                "tool": name
            }, ensure_ascii=False)
        )]
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "tool": name,
                "type": type(e).__name__
            }, ensure_ascii=False)
        )]


async def handle_configure_proxies(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle configure_proxies tool."""
    global _proxy_pool
    
    proxy_entries = parse_proxy_source(
        arguments.get("proxies"),
        arguments.get("proxies_text"),
        arguments.get("proxies_file"),
    )
    if not proxy_entries:
        return {"error": "At least one proxy entry must be provided"}

    rotation_strategy_str = arguments.get("rotation_strategy", "round_robin")
    health_check_interval = arguments.get("health_check_interval", 300)
    username = arguments.get("username")
    password = arguments.get("password")
    default_scheme = arguments.get("default_scheme", "http")
    replace_existing = arguments.get("replace_existing", True)
    fail_closed = arguments.get("fail_closed", False)
    
    try:
        strategy = RotationStrategy(rotation_strategy_str.lower())
    except ValueError:
        return {
            "error": f"Invalid rotation strategy: {rotation_strategy_str}. Must be one of: round_robin, random, sticky, least_used"
        }
    
    new_proxy_pool = ProxyPool(
        rotation_strategy=strategy,
        health_check_interval=health_check_interval,
        fail_closed=fail_closed,
    ) if replace_existing or not _proxy_pool else _proxy_pool
    new_proxy_pool.rotation_strategy = strategy
    new_proxy_pool.health_check_interval = health_check_interval
    new_proxy_pool.fail_closed = fail_closed
    try:
        for proxy_entry in proxy_entries:
            new_proxy_pool.add_proxy(proxy_entry, username, password, default_scheme)
    except ValueError as exc:
        return {"error": str(exc)}
    
    # Update browser pool with new proxy pool
    browser_pool.set_proxy_pool(new_proxy_pool)
    _proxy_pool = new_proxy_pool
    set_http_proxy_pool(_proxy_pool)
    
    # Run initial health check
    health_results = await _proxy_pool.health_check_all()
    
    return {
        "status": "configured",
        "proxies_count": len(_proxy_pool.proxies),
        "rotation_strategy": rotation_strategy_str,
        "health_check_interval": health_check_interval,
        "initial_health": health_results,
        "stats": _proxy_pool.get_stats(),
        "timestamp": datetime.now().isoformat(),
    }


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_deep_analyze(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle deep_analyze tool with comprehensive error handling."""
    url = arguments["url"]
    depth = arguments.get("depth", "full")
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            # Start network interception
            await network_interceptor.start_intercepting(page)
            
            # Navigate to URL
            response = await navigate_to_url(page, url)
            
            # Get page content
            content = await page.content()
            
            # Analyze network
            requests = await network_interceptor.capture_all_requests()
            responses = await network_interceptor.capture_all_responses()
            
            # Discover APIs
            api_discovery.detect_rest_endpoints(requests, responses)
            graphql_endpoint = api_discovery.detect_graphql(requests, responses)
            
            # Analyze security
            protection_type = bot_detector.detect_protection_type(content, {})
            fingerprinting = bot_detector.analyze_fingerprinting(content)
            
            # Analyze JavaScript
            js_code = await page.evaluate("() => document.documentElement.outerHTML")
            api_calls = js_analyzer.extract_api_calls(js_code)
            
            result = {
                "url": url,
                "depth": depth,
                "apis": {
                    "rest": len(api_discovery.discovered_apis),
                    "graphql": 1 if graphql_endpoint else 0,
                    "websocket": len(network_interceptor.websockets),
                },
                "protection": protection_type.value if protection_type else "none",
                "fingerprinting": {
                    "canvas": fingerprinting.canvas_fingerprint,
                    "webgl": fingerprinting.webgl_fingerprint,
                    "audio": fingerprinting.audio_fingerprint,
                },
                "network_requests": len(requests),
                "api_calls_found": len(api_calls),
                "timestamp": datetime.now().isoformat(),
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error in deep_analyze for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_discover_apis(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discover_apis tool."""
    url = arguments["url"]
    include_hidden = arguments.get("include_hidden", True)
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            await network_interceptor.start_intercepting(page)
            response = await navigate_to_url(page, url)
            
            requests = await network_interceptor.capture_all_requests()
            responses = await network_interceptor.capture_all_responses()
            
            # Discover APIs
            rest_endpoints = api_discovery.detect_rest_endpoints(requests, responses)
            graphql_endpoint = api_discovery.detect_graphql(requests, responses)
            
            internal_apis = []
            if include_hidden:
                internal_apis = api_discovery.find_undocumented_endpoints(requests)
            
            result = {
                "url": url,
                "rest_endpoints": [
                    {
                        "url": ep.url,
                        "method": ep.method,
                        "path": ep.path,
                    }
                    for ep in rest_endpoints
                ],
                "graphql": {
                    "url": graphql_endpoint.url if graphql_endpoint else None,
                },
                "internal_apis": [
                    {
                        "url": api.url,
                        "method": api.method,
                        "confidence": api.confidence,
                    }
                    for api in internal_apis
                ],
                "timestamp": datetime.now().isoformat(),
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error in discover_apis for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_introspect_graphql(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle introspect_graphql tool."""
    endpoint = arguments["endpoint"]
    
    try:
        schema = await asyncio.wait_for(
            api_discovery.run_introspection(endpoint),
            timeout=config.request_timeout
        )
        
        if schema:
            operations = api_discovery.extract_queries_mutations(schema)
            return {
                "endpoint": endpoint,
                "schema": schema,
                "operations": [
                    {
                        "name": op.name,
                        "type": op.type,
                    }
                    for op in operations
                ],
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "endpoint": endpoint,
                "error": "Introspection failed or not enabled",
                "timestamp": datetime.now().isoformat(),
            }
    
    except Exception as e:
        logger.error(f"Error in introspect_graphql for {endpoint}: {e}", exc_info=True)
        raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_analyze_websocket(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_websocket tool."""
    url = arguments["url"]
    wait_time = arguments.get("wait_time", 5)
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            await network_interceptor.start_intercepting(page)
            response = await navigate_to_url(page, url)
            
            # Wait for WebSocket connections
            await asyncio.sleep(wait_time)
            
            ws_session = await network_interceptor.intercept_websocket()
            
            if ws_session:
                messages = await network_interceptor.decode_ws_messages(ws_session.url)
                return {
                    "url": ws_session.url,
                    "messages": [
                        {
                            "direction": msg.direction,
                            "message": msg.message[:100] + "..." if len(msg.message) > 100 else msg.message,
                            "type": msg.message_type,
                        }
                        for msg in messages[:10]  # Limit to first 10
                    ],
                    "total_messages": len(messages),
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return {
                    "url": url,
                    "error": "No WebSocket connections found",
                    "timestamp": datetime.now().isoformat(),
                }
        
        except Exception as e:
            logger.error(f"Error in analyze_websocket for {url}: {e}", exc_info=True)
            raise


async def handle_record_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle record_session tool."""
    url = arguments["url"]
    auto_save = arguments.get("auto_save", True)
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    try:
        context = await create_stealth_context(browser_pool, url=url)
        page = await context.new_page()
        page.set_default_timeout(config.navigation_timeout * 1000)
        await apply_stealth_to_page(context, page)
        
        recorder = SessionRecorder()
        recording = await recorder.start_recording(page)
        
        # Register with storage
        recording_storage.register_active_recording(recording)
        
        # Navigate to URL
        response = await navigate_to_url(page, url)
        
        # Store active recording
        _active_recordings[recording.id] = (recorder, page, context)
        
        return {
            "recording_id": recording.id,
            "status": "recording",
            "url": url,
            "auto_save": auto_save,
            "message": "Session recording started. Use stop_recording to finish.",
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error starting recording for {url}: {e}", exc_info=True)
        raise


async def handle_stop_recording(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle stop_recording tool."""
    recording_id = arguments["recording_id"]
    save = arguments.get("save", True)
    
    if recording_id not in _active_recordings:
        return {
            "error": f"Recording {recording_id} not found or already stopped",
            "recording_id": recording_id,
        }
    
    try:
        recorder, page, context = _active_recordings[recording_id]
        
        # Stop recording
        recording = await recorder.stop_recording()
        
        if not recording:
            return {
                "error": "Failed to stop recording",
                "recording_id": recording_id,
            }
        
        # Save if requested
        file_path = None
        if save or config.auto_save_recordings:
            file_path = recording_storage.save_recording(recording)
        
        # Cleanup - only close page, let pool manage context
        try:
            await page.close()
        except Exception as e:
            logger.warning(f"Error cleaning up recording {recording_id}: {e}")
        
        # Remove from active recordings
        del _active_recordings[recording_id]
        recording_storage.unregister_active_recording(recording_id)
        
        return {
            "recording_id": recording_id,
            "status": "stopped",
            "duration": recording.duration,
            "events_count": len(recording.events),
            "snapshots_count": len(recording.state_snapshots),
            "network_events_count": len(recording.network),
            "saved": save or config.auto_save_recordings,
            "file_path": file_path,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error stopping recording {recording_id}: {e}", exc_info=True)
        raise


async def handle_list_recordings(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_recordings tool."""
    status_filter = arguments.get("status", "all")
    
    try:
        all_recordings = recording_storage.list_recordings()
        
        if status_filter == "active":
            recordings = [r for r in all_recordings if r.get("status") == "active"]
        elif status_filter == "saved":
            recordings = [r for r in all_recordings if r.get("status") == "saved"]
        else:
            recordings = all_recordings
        
        return {
            "recordings": recordings,
            "total": len(recordings),
            "active": len([r for r in recordings if r.get("status") == "active"]),
            "saved": len([r for r in recordings if r.get("status") == "saved"]),
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error listing recordings: {e}", exc_info=True)
        raise


async def handle_get_recording_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_recording_status tool."""
    recording_id = arguments["recording_id"]
    
    try:
        # Check if active
        if recording_id in _active_recordings:
            recorder, page, context = _active_recordings[recording_id]
            recording = recorder._recording if recorder._recording else None
            
            if recording:
                return {
                    "recording_id": recording_id,
                    "status": "active",
                    "start_time": recording.start_time.isoformat() if recording.start_time else None,
                    "duration": recording.duration,
                    "events_count": len(recording.events),
                    "snapshots_count": len(recording.state_snapshots),
                    "network_events_count": len(recording.network),
                }
        
        # Try loading from storage
        try:
            recording = recording_storage.load_recording(recording_id)
        except (RecordingNotFoundError, RecordingExpiredError) as exc:
            return {
                "error": str(exc),
                "recording_id": recording_id,
            }

        return {
            "recording_id": recording_id,
            "status": "saved",
            "start_time": recording.start_time.isoformat() if recording.start_time else None,
            "end_time": recording.end_time.isoformat() if recording.end_time else None,
            "duration": recording.duration,
            "events_count": len(recording.events),
            "snapshots_count": len(recording.state_snapshots),
            "network_events_count": len(recording.network),
        }

    except Exception as e:
        logger.error(f"Error getting recording status for {recording_id}: {e}", exc_info=True)
        raise


async def handle_generate_crawler(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle generate_crawler tool."""
    recording_id = arguments["recording_id"]
    output_format = arguments.get("output_format", "yaml")
    
    try:
        # Load recording from storage
        try:
            recording = recording_storage.load_recording(recording_id)
        except (RecordingNotFoundError, RecordingExpiredError) as exc:
            return {
                "error": str(exc),
                "recording_id": recording_id,
            }

        # Generate crawler
        generator = CrawlerGenerator()
        crawler_def = generator.from_recording(recording)
        crawler_def = generator.optimize_crawler(crawler_def)
        
        # Convert to requested format
        if output_format == "yaml":
            output = generator.to_yaml(crawler_def)
        elif output_format == "python":
            output = generator.to_python_code(crawler_def)
        elif output_format == "playwright":
            output = generator.to_playwright_script(crawler_def)
        else:
            output = generator.to_yaml(crawler_def)
        
        return {
            "recording_id": recording_id,
            "output_format": output_format,
            "status": "generated",
            "crawler": {
                "name": crawler_def.name,
                "description": crawler_def.description,
                "steps_count": len(crawler_def.steps),
            },
            "output": output,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error generating crawler from {recording_id}: {e}", exc_info=True)
        raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_analyze_auth(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_auth tool."""
    url = arguments["url"]
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            await network_interceptor.start_intercepting(page)
            response = await navigate_to_url(page, url)
            
            requests = await network_interceptor.capture_all_requests()
            
            auth_requests = []
            for req in requests:
                analyzed = request_analyzer.analyze(req)
                if analyzed.auth_type.value != "none":
                    auth_requests.append({
                        "url": analyzed.url,
                        "auth_type": analyzed.auth_type.value,
                    })
            
            return {
                "url": url,
                "auth_flows": auth_requests,
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error in analyze_auth for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_detect_protection(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle detect_protection tool."""
    url = arguments["url"]
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            content = await page.content()
            
            headers = response.headers if response else {}
            
            protection_type = bot_detector.detect_protection_type(content, headers)
            fingerprinting = bot_detector.analyze_fingerprinting(content)
            captcha_type = bot_detector.detect_captcha_type(content)
            
            return {
                "url": url,
                "protection_type": protection_type.value if protection_type else "none",
                "captcha_type": captcha_type.value if captcha_type else "none",
                "fingerprinting": {
                    "canvas": fingerprinting.canvas_fingerprint,
                    "webgl": fingerprinting.webgl_fingerprint,
                    "audio": fingerprinting.audio_fingerprint,
                },
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error in detect_protection for {url}: {e}", exc_info=True)
            raise


async def handle_deobfuscate_js(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle deobfuscate_js tool.

    Static analysis only — does not execute the payload — but still enforces
    the length cap so the deobfuscator can't be DoS'd by gigantic input.
    """
    code = arguments["code"]

    if not code or not isinstance(code, str):
        return {
            "error": "Invalid code: must be a non-empty string",
        }
    if len(code) > config.js_max_length:
        raise ValidationError(
            f"'code' length {len(code)} exceeds limit {config.js_max_length}"
        )
    
    try:
        # Detect obfuscation type
        obfuscation_type = js_deobfuscator.detect_obfuscation_type(code)
        
        # Deobfuscate based on type
        deobfuscated = code
        if obfuscation_type.value == "string_encoding":
            deobfuscated = js_deobfuscator.deobfuscate_strings(code)
        elif obfuscation_type.value == "control_flow_flattening":
            deobfuscated = js_deobfuscator.simplify_control_flow(code)
        else:
            # Try all deobfuscation methods
            deobfuscated = js_deobfuscator.deobfuscate_strings(code)
            deobfuscated = js_deobfuscator.simplify_control_flow(deobfuscated)
        
        # Extract original names if possible
        name_map = js_deobfuscator.extract_original_names(code)
        
        improvement = "0%"
        if code:
            size_change = ((len(code) - len(deobfuscated)) / len(code) * 100)
            improvement = f"{size_change:.1f}% size change"
        
        return {
            "original_length": len(code),
            "deobfuscated_length": len(deobfuscated),
            "obfuscation_type": obfuscation_type.value,
            "deobfuscated": deobfuscated,
            "extracted_names": name_map,
            "improvement": improvement,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error deobfuscating JS: {e}", exc_info=True)
        raise


async def handle_extract_from_js(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_from_js tool."""
    code = arguments["code"]
    
    if not code or not isinstance(code, str):
        return {
            "error": "Invalid code: must be a non-empty string",
        }
    
    try:
        api_calls = js_analyzer.extract_api_calls(code)
        urls = js_analyzer.find_hardcoded_urls(code)
        constants = js_analyzer.extract_constants(code)
        auth_logic = js_analyzer.find_auth_logic(code)
        
        return {
            "api_calls": [
                {
                    "url": call.url,
                    "method": call.method,
                    "type": call.type,
                }
                for call in api_calls
            ],
            "hardcoded_urls": urls,
            "constants": constants,
            "auth_logic": {
                "flow_type": auth_logic.flow_type if auth_logic else None,
                "token_storage": auth_logic.token_storage if auth_logic else None,
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error extracting from JS: {e}", exc_info=True)
        raise


async def handle_health_check(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle health_check tool."""
    try:
        # Check browser pool
        pool_stats = browser_pool.get_stats()
        
        # Check storage
        recordings = recording_storage.list_recordings()
        
        # Check active recordings
        active_count = len(_active_recordings)
        
        # Get rate limiter stats
        rate_limiter_stats = rate_limiter.get_stats()
        
        health_status = {
            "status": "healthy",
            "browser_pool": {
                "size": pool_stats["size"],
                "max_size": pool_stats["max_size"],
                "healthy": pool_stats["size"] <= pool_stats["max_size"],
            },
            "storage": {
                "recordings_count": len(recordings),
                "active_recordings": active_count,
                "healthy": True,
            },
            "rate_limiter": rate_limiter_stats,
            "config": {
                "navigation_timeout": config.navigation_timeout,
                "operation_timeout": config.operation_timeout,
                "max_retries": config.max_retries,
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        # Determine overall health
        if not health_status["browser_pool"]["healthy"]:
            health_status["status"] = "degraded"
        
        return health_status
    
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


async def handle_save_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle save_session tool."""
    session_id = arguments["session_id"]
    url = arguments.get("url")

    try:
        if url:
            # Capture live browser state by navigating to the URL
            context = await create_stealth_context(browser_pool, url=url)
            page = await context.new_page()
            page.set_default_timeout(config.navigation_timeout * 1000)
            await apply_stealth_to_page(context, page)
            try:
                await navigate_to_url(page, url)

                # Extract cookies
                raw_cookies = await context.cookies()
                cookies = {c["name"]: c["value"] for c in raw_cookies}

                # Extract localStorage
                local_storage = {}
                try:
                    local_storage = await page.evaluate("""() => {
                        const s = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const k = localStorage.key(i);
                            s[k] = localStorage.getItem(k);
                        }
                        return s;
                    }""")
                except (PlaywrightError, AttributeError):
                    pass

                # Extract sessionStorage
                session_storage = {}
                try:
                    session_storage = await page.evaluate("""() => {
                        const s = {};
                        for (let i = 0; i < sessionStorage.length; i++) {
                            const k = sessionStorage.key(i);
                            s[k] = sessionStorage.getItem(k);
                        }
                        return s;
                    }""")
                except Exception:
                    pass
            finally:
                try:
                    await page.close()
                except (PlaywrightError, AttributeError) as exc:
                    logger.warning("Error closing save_session page: %s", exc)

            await session_manager.save_session_state(
                session_id,
                cookies=cookies,
                local_storage=local_storage,
                session_storage=session_storage,
            )
            await session_manager.persist_to_disk()
            return {
                "status": "saved",
                "session_id": session_id,
                "cookies_count": len(cookies),
                "local_storage_count": len(local_storage),
                "session_storage_count": len(session_storage),
                "timestamp": datetime.now().isoformat(),
            }
        else:
            # Persist an already-existing session (created via create_session)
            result = await session_manager.save_session(session_id)
            return result

    except Exception as e:
        logger.error(f"Error saving session {session_id}: {e}", exc_info=True)
        return {
            "error": str(e),
            "session_id": session_id,
        }


async def handle_load_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle load_session tool."""
    session_id = arguments["session_id"]
    
    try:
        session = await session_manager.load_session_state(session_id)
        
        if not session:
            return {
                "error": f"Session {session_id} not found",
                "session_id": session_id,
            }
        
        # Return session info - actual application to browser context
        # would happen when creating a new browser context
        return {
            "status": "loaded",
            "session_id": session_id,
            "cookies_count": len(session.cookies),
            "local_storage_count": len(session.local_storage),
            "session_storage_count": len(session.session_storage),
            "created_at": session.created_at.isoformat(),
            "last_used": session.last_used.isoformat(),
            "user_data_dir": str(session_manager.get_user_data_dir(session_id)) if session_manager.get_user_data_dir(session_id) else None,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error loading session {session_id}: {e}", exc_info=True)
        return {
            "error": str(e),
            "session_id": session_id,
        }


async def handle_list_sessions(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_sessions tool."""
    try:
        sessions = await session_manager.list_sessions()
        
        return {
            "sessions": sessions,
            "total": len(sessions),
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error listing sessions: {e}", exc_info=True)
        return {
            "error": str(e),
            "sessions": [],
        }


async def handle_analyze_sitemap(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_sitemap tool."""
    if not sitemap_analyzer:
        return {"error": "Sitemap analyzer not available"}
    
    sitemap_url = arguments["sitemap_url"]
    
    try:
        analysis = await sitemap_analyzer.analyze_sitemap(sitemap_url)
        
        return {
            "sitemap_url": sitemap_url,
            "sitemap_type": analysis.sitemap_type,
            "total_urls": analysis.total_urls,
            "entries": [
                {
                    "url": entry.url,
                    "lastmod": entry.lastmod,
                    "changefreq": entry.changefreq,
                    "priority": entry.priority,
                }
                for entry in analysis.entries[:100]  # Limit to first 100
            ],
            "errors": analysis.errors,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error analyzing sitemap {sitemap_url}: {e}", exc_info=True)
        return {
            "error": str(e),
            "sitemap_url": sitemap_url,
        }


async def handle_check_robots(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle check_robots tool."""
    if not sitemap_analyzer:
        return {"error": "Sitemap analyzer not available"}
    
    url = arguments["url"]
    
    try:
        analysis = await sitemap_analyzer.analyze_robots(url)
        
        return {
            "robots_url": analysis.robots_url,
            "valid": analysis.valid,
            "rules": [
                {
                    "user_agent": rule.user_agent,
                    "allow": rule.allow,
                    "disallow": rule.disallow,
                    "crawl_delay": rule.crawl_delay,
                }
                for rule in analysis.rules
            ],
            "sitemaps": analysis.sitemaps,
            "errors": analysis.errors,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error checking robots.txt for {url}: {e}", exc_info=True)
        return {
            "error": str(e),
            "url": url,
        }


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_take_screenshot(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle take_screenshot tool."""
    import base64
    
    url = arguments["url"]
    full_page = arguments.get("full_page", False)
    wait_for = arguments.get("wait_for")
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            # Navigate to URL
            response = await navigate_to_url(page, url)
            
            # Wait for selector if specified
            if wait_for and wait_for not in ["load", "networkidle"]:
                await page.wait_for_selector(wait_for, timeout=10000)
            
            # Take screenshot
            screenshot_bytes = await page.screenshot(full_page=full_page)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            return {
                "url": url,
                "full_page": full_page,
                "screenshot": screenshot_b64,
                "format": "png",
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error taking screenshot of {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_extract_article(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_article tool."""
    url = arguments["url"]
    include_images = arguments.get("include_images", True)
    output_format = arguments.get("output_format", "text")
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            html = await page.content()
            
            # Extract content
            extracted = content_extractor.extract(
                html,
                url=url,
                include_images=include_images,
                output_format=output_format,
            )
            
            return {
                "url": url,
                "title": extracted.title,
                "text": extracted.text,
                "markdown": extracted.markdown,
                "author": extracted.author,
                "date": extracted.date,
                "language": extracted.language,
                "images": extracted.images,
                "categories": extracted.categories,
                "tags": extracted.tags,
                "metadata": extracted.metadata,
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error extracting article from {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_solve_captcha(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle deprecated solve_captcha tool with detection-only behavior."""
    url = arguments["url"]

    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)

    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            content = await page.content()
            detected_type = bot_detector.detect_captcha_type(content)
            protection_type = bot_detector.detect_protection_type(content, response.headers if response else {})

            return {
                "url": url,
                "detected_type": detected_type.value if detected_type else "none",
                "protection_type": protection_type.value if protection_type else "none",
                "status": "manual_review_required" if detected_type.value != "none" else "no_captcha_detected",
                "solved": False,
                "deprecated": True,
                "message": (
                    "CAPTCHA solving automation is disabled. If you are authorized to access this site, "
                    "complete any human verification manually in an approved workflow."
                ),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error detecting CAPTCHA on {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_detect_technology(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle detect_technology tool."""
    url = arguments["url"]
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            html = await page.content()
            headers = dict(response.headers) if response else {}
            
            # Detect technologies
            stack = technology_detector.detect(html, url, headers)
            protection_techs = technology_detector.get_protection_technologies(stack)
            
            return {
                "url": url,
                "cms": [{"name": t.name, "version": t.version} for t in stack.cms],
                "frameworks": [{"name": t.name, "version": t.version} for t in stack.frameworks],
                "programming_languages": [{"name": t.name, "version": t.version} for t in stack.programming_languages],
                "web_servers": [{"name": t.name, "version": t.version} for t in stack.web_servers],
                "databases": [{"name": t.name, "version": t.version} for t in stack.databases],
                "cdn": [{"name": t.name, "version": t.version} for t in stack.cdn],
                "analytics": [{"name": t.name, "version": t.version} for t in stack.analytics],
                "advertising": [{"name": t.name, "version": t.version} for t in stack.advertising],
                "javascript_libraries": [{"name": t.name, "version": t.version} for t in stack.javascript_libraries],
                "protection_technologies": protection_techs,
                "other": [{"name": t.name, "version": t.version} for t in stack.other],
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error detecting technology for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_smart_extract(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle smart_extract tool.
    
    Uses pattern-based extraction (free, no API required).
    Optionally uses LLM for enhanced results if OpenAI API key is configured.
    """
    url = arguments["url"]
    query = arguments["query"]
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            html = await page.content()
            
            # Smart extract using pattern-based extraction (always available)
            result = smart_extractor.extract(html, query)
            
            return {
                "url": url,
                "query": query,
                "targets": [
                    {
                        "description": t.description,
                        "selector_type": t.selector_type,
                        "selector": t.selector,
                    }
                    for t in result.targets
                ],
                "extracted_data": result.extracted_data,
                "confidence": result.confidence,
                "llm_enhanced": smart_extractor.llm_enabled,
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error in smart_extract for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_convert_to_markdown(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle convert_to_markdown tool."""
    url = arguments["url"]
    css_selector = arguments.get("css_selector")
    exclude_selectors = arguments.get("exclude_selectors")
    
    # Apply rate limiting
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            html = await page.content()
            
            # Convert to markdown
            markdown = content_extractor.extract_to_markdown(
                html,
                url,
                css_selector=css_selector,
                exclude_selectors=exclude_selectors,
            )
            
            return {
                "url": url,
                "markdown": markdown,
                "length": len(markdown),
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error converting {url} to markdown: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_crawl(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle recursive crawling of a website up to limit depth and pages."""
    seed_url = arguments["url"]
    max_depth = min(max(int(arguments.get("max_depth", 2)), 1), 5)
    max_pages = min(max(int(arguments.get("max_pages", 10)), 1), 100)
    concurrency = min(max(int(arguments.get("concurrency", 3)), 1), 10)
    ignore_external = arguments.get("ignore_external", True)
    save_to_file = arguments.get("save_to_file", False)
    css_selector = arguments.get("css_selector")
    exclude_selectors = arguments.get("exclude_selectors")

    from urllib.parse import urlparse
    parsed_seed = urlparse(seed_url)
    base_domain = parsed_seed.netloc

    # State tracking
    visited = {seed_url}
    results = {}
    
    # Queue-based recursive crawling
    queue = asyncio.Queue()
    await queue.put((seed_url, 1)) # (url, current_depth)
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def worker():
        while True:
            try:
                url, depth = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break
                
            async with semaphore:
                # Apply rate limiting
                await rate_limiter.wait_if_needed(url)

                try:
                    logger.info(f"Crawling URL: {url} (Depth: {depth}/{max_depth})")
                    async with browser_context_manager(url=url) as page:
                        response = await navigate_to_url(page, url)
                        html = await page.content()
                        title = await page.title()

                        # Convert to markdown
                        markdown = content_extractor.extract_to_markdown(
                            html,
                            url,
                            css_selector=css_selector,
                            exclude_selectors=exclude_selectors,
                        )
                        
                        # Extract links
                        links_data = await page.evaluate("""
                            () => {
                                return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                                    href: a.href,
                                    text: a.textContent.trim()
                                }));
                            }
                        """)
                        
                        internal_links = []
                        external_links = []
                        
                        for link in links_data:
                            href = link.get("href", "").strip()
                            if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
                                continue
                            
                            clean_href = href.split('#')[0]
                            parsed_link = urlparse(clean_href)
                            
                            if parsed_link.scheme not in ("http", "https"):
                                continue
                                
                            is_internal = parsed_link.netloc == base_domain
                            
                            if is_internal:
                                internal_links.append(clean_href)
                                if clean_href not in visited and depth < max_depth and len(visited) < max_pages:
                                    visited.add(clean_href)
                                    await queue.put((clean_href, depth + 1))
                            else:
                                external_links.append(clean_href)
                                if not ignore_external and clean_href not in visited and depth < max_depth and len(visited) < max_pages:
                                    visited.add(clean_href)
                                    await queue.put((clean_href, depth + 1))
                                    
                        results[url] = {
                            "title": title,
                            "markdown": markdown[:5000] + "..." if len(markdown) > 5000 else markdown, # limit size in return
                            "depth": depth,
                            "links": {
                                "internal_count": len(internal_links),
                                "external_count": len(external_links)
                            }
                        }
                except Exception as e:
                    logger.error(f"Error crawling page {url}: {e}")
                    results[url] = {
                        "error": str(e),
                        "depth": depth
                    }
                finally:
                    queue.task_done()

    # Launch concurrent worker tasks
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers)
    
    response_data = {
        "seed_url": seed_url,
        "pages_crawled": len(results),
        "max_depth": max_depth,
        "max_pages": max_pages,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }
    
    if save_to_file:
        try:
            os.makedirs(".crawls", exist_ok=True)
            safe_domain = "".join(c for c in base_domain if c.isalnum() or c in ".-_").rstrip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.abspath(f".crawls/crawl_{safe_domain}_{timestamp}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(response_data, f, indent=2, ensure_ascii=False)
            response_data["saved_to_file"] = filepath
        except Exception as e:
            logger.error(f"Failed to save crawl to file: {e}")
            response_data["save_error"] = str(e)
            
    return response_data


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_structured_extract(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle structured_extract tool using LLM directly on page markdown."""
    url = arguments["url"]
    schema = arguments["schema"]
    instructions = arguments.get("instructions")
    css_selector = arguments.get("css_selector")
    exclude_selectors = arguments.get("exclude_selectors")
    
    if not smart_extractor.llm_enabled or not smart_extractor.client:
        return {
            "error": (
                "LLM extraction is not configured. Please set the CRAWLEMOON_LLM_PROVIDER "
                "and CRAWLEMOON_LLM_API_KEY environment variables to use structured_extract. "
                "Supported providers include openrouter, groq, together, ollama (local), or openai."
            )
        }
        
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            html = await page.content()
            
            # Convert to markdown with filtering options
            markdown = content_extractor.extract_to_markdown(
                html,
                url,
                css_selector=css_selector,
                exclude_selectors=exclude_selectors,
            )
            markdown_sample = markdown[:16000] if len(markdown) > 16000 else markdown
            
            instruction_text = f"\nAdditional Instructions: {instructions}" if instructions else ""
            
            prompt = f"""You are a precise data extraction AI. Extract structured data from the following webpage markdown according to the target JSON schema.
            
Webpage Markdown:
{markdown_sample}

Target JSON Schema:
{json.dumps(schema, indent=2)}
{instruction_text}

Respond STRICTLY with a valid JSON object matching the target JSON schema. No explanations, no markdown formatting blocks, just the raw JSON object."""

            try:
                try:
                    # Try with JSON mode
                    response = smart_extractor.client.chat.completions.create(
                        model=smart_extractor.model,
                        messages=[
                            {"role": "system", "content": "You are a specialized JSON extraction assistant that only outputs valid JSON matching the requested schema. Do not enclose in markdown blocks."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        max_tokens=2000,
                    )
                except Exception as json_mode_err:
                    logger.warning(f"JSON mode failed, retrying without response_format: {json_mode_err}")
                    response = smart_extractor.client.chat.completions.create(
                        model=smart_extractor.model,
                        messages=[
                            {"role": "system", "content": "You are a specialized JSON extraction assistant that only outputs valid JSON matching the requested schema. Do not enclose in markdown blocks."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1,
                        max_tokens=2000,
                    )
                
                content = response.choices[0].message.content.strip()
                
                # Robustly strip markdown json code block fences if present
                import re
                json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                if json_match:
                    content = json_match.group(1).strip()
                    
                extracted_json = json.loads(content)
                
                return {
                    "url": url,
                    "extracted_data": extracted_json,
                    "model": smart_extractor.model,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as llm_err:
                logger.error(f"LLM call failed for structured_extract: {llm_err}")
                return {
                    "error": f"LLM extraction failed: {str(llm_err)}",
                    "url": url
                }
                
        except Exception as e:
            logger.error(f"Error in handle_structured_extract for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_stealth_request(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle stealth_request tool."""
    from ..core.http.stealth_client import create_stealth_client
    
    url = arguments["url"]
    method = arguments.get("method", "GET")
    browser = arguments.get("browser", "chrome")
    headers = arguments.get("headers", {})
    data = arguments.get("data")
    
    try:
        proxies = None
        selected_proxy = None
        if _proxy_pool:
            from urllib.parse import urlparse

            selected_proxy = await _proxy_pool.get_proxy(domain=urlparse(url).netloc)
            if selected_proxy:
                proxies = selected_proxy.to_curl_cffi_proxies()

        # Create stealth client
        client = create_stealth_client(browser=browser, proxies=proxies)
        
        # Make request
        if method == "GET":
            response = client.get(url, headers=headers)
        elif method == "POST":
            response = client.post(url, headers=headers, json=data)
        elif method == "PUT":
            response = client.request("PUT", url, headers=headers, json=data)
        elif method == "DELETE":
            response = client.request("DELETE", url, headers=headers)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        return {
            "url": url,
            "method": method,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.text[:10000],  # Limit content size
            "content_length": len(response.text),
            "proxy": selected_proxy.masked_url() if selected_proxy else None,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error in stealth_request for {url}: {e}", exc_info=True)
        raise


# ============================================================================
# Cache Management Handlers
# ============================================================================

async def handle_clear_cache(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle clear_cache tool."""
    cache_type = arguments.get("cache_type", "all")
    
    try:
        if cache_type == "all":
            cache_manager.clear()
        else:
            cache_manager.clear(cache_type)
        
        return {
            "status": "cleared",
            "cache_type": cache_type,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        raise


async def handle_get_cache_stats(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_cache_stats tool."""
    try:
        stats = cache_manager.get_stats()
        return {
            **stats,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        raise


# ============================================================================
# Rate Limiter Configuration Handlers
# ============================================================================

async def handle_configure_rate_limit(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle configure_rate_limit tool."""
    domain = arguments.get("domain")
    requests_per_second = arguments.get("requests_per_second", 1.0)
    requests_per_minute = arguments.get("requests_per_minute")
    requests_per_hour = arguments.get("requests_per_hour")
    
    try:
        if domain:
            rate_limiter.set_domain_rate_limit(
                domain=domain,
                requests_per_second=requests_per_second,
                requests_per_minute=requests_per_minute,
                requests_per_hour=requests_per_hour,
            )
            return {
                "status": "configured",
                "type": "domain",
                "domain": domain,
                "requests_per_second": requests_per_second,
                "requests_per_minute": requests_per_minute,
                "requests_per_hour": requests_per_hour,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            rate_limiter.set_default_rate_limit(
                requests_per_second=requests_per_second,
                requests_per_minute=requests_per_minute,
                requests_per_hour=requests_per_hour,
            )
            return {
                "status": "configured",
                "type": "default",
                "requests_per_second": requests_per_second,
                "requests_per_minute": requests_per_minute,
                "requests_per_hour": requests_per_hour,
                "timestamp": datetime.now().isoformat(),
            }
    except Exception as e:
        logger.error(f"Error configuring rate limit: {e}", exc_info=True)
        raise


async def handle_get_rate_limit_stats(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_rate_limit_stats tool."""
    try:
        stats = rate_limiter.get_stats()
        return {
            **stats,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting rate limit stats: {e}", exc_info=True)
        raise


# ============================================================================
# Proxy Management Handlers
# ============================================================================

async def handle_get_proxy_stats(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_proxy_stats tool."""
    try:
        if _proxy_pool:
            stats = _proxy_pool.get_stats()
            return {
                **stats,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "status": "no_proxy_pool",
                "message": "No proxy pool configured. Use configure_proxies to set up proxies.",
                "timestamp": datetime.now().isoformat(),
            }
    except Exception as e:
        logger.error(f"Error getting proxy stats: {e}", exc_info=True)
        raise


async def handle_add_proxy(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle add_proxy tool."""
    global _proxy_pool
    
    proxy_url = arguments["proxy_url"]
    username = arguments.get("username")
    password = arguments.get("password")
    default_scheme = arguments.get("default_scheme", "http")
    
    try:
        if not _proxy_pool:
            # Create a new proxy pool if none exists
            _proxy_pool = ProxyPool(
                rotation_strategy=RotationStrategy.ROUND_ROBIN,
            )
            _proxy_pool.add_proxy(proxy_url, username, password, default_scheme)
            browser_pool.set_proxy_pool(_proxy_pool)
        else:
            _proxy_pool.add_proxy(proxy_url, username, password, default_scheme)
        set_http_proxy_pool(_proxy_pool)

        proxy = ProxyPool.normalize_proxy(proxy_url, username, password, default_scheme)
        
        return {
            "status": "added",
            "proxy_url": proxy.masked_url(),
            "total_proxies": len(_proxy_pool.proxies) if _proxy_pool else 0,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error adding proxy: {e}", exc_info=True)
        raise


async def handle_remove_proxy(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle remove_proxy tool."""
    proxy_url = arguments["proxy_url"]
    
    try:
        if not _proxy_pool:
            return {
                "error": "No proxy pool configured",
                "proxy_url": proxy_url,
            }
        
        removed = _proxy_pool.remove_proxy(proxy_url)
        
        return {
            "status": "removed" if removed else "not_found",
            "proxy_url": proxy_url,
            "total_proxies": len(_proxy_pool.proxies),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error removing proxy: {e}", exc_info=True)
        raise


async def handle_test_proxy(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle test_proxy tool."""
    proxy_url = arguments["proxy_url"]
    username = arguments.get("username")
    password = arguments.get("password")
    default_scheme = arguments.get("default_scheme", "http")
    
    try:
        proxy = ProxyPool.normalize_proxy(proxy_url, username, password, default_scheme)
        
        # Create temporary pool for testing
        temp_pool = ProxyPool(proxies=[], health_check_timeout=10.0)
        temp_pool.proxies.append(proxy)
        
        is_healthy = await temp_pool.health_check(proxy, test_url=test_url)
        
        return {
            "proxy_url": proxy.masked_url(),
            "healthy": is_healthy,
            "proxy_type": proxy.proxy_type.value,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error testing proxy: {e}", exc_info=True)
        return {
            "proxy_url": proxy_url,
            "healthy": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


# ============================================================================
# Xray / V2ray Proxy Engine Handlers
# ============================================================================

async def handle_configure_xray_subscription(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle configure_xray_subscription tool."""
    global _xray_manager, _proxy_pool
    
    subscription_url = arguments.get("subscription_url")
    raw_links = arguments.get("raw_links")
    num_ports = arguments.get("num_ports", 3)
    start_port = arguments.get("start_port", 10801)
    auto_benchmark = arguments.get("auto_benchmark", True)
    test_url = arguments.get("test_url", "http://httpbin.org/ip")
    
    if not subscription_url and not raw_links:
        return {
            "error": "Either subscription_url or raw_links must be provided"
        }
        
    try:
        # Stop any existing Xray manager to clean up resources
        if _xray_manager:
            _xray_manager.stop_all()
            
        _xray_manager = CrawlemoonV2rayManager(subscription_url=subscription_url)
        _xray_manager.initialize()
        
        num_loaded = 0
        if subscription_url:
            num_loaded = await _xray_manager.fetch_subscription()
        elif raw_links:
            num_loaded = _xray_manager.load_raw_links(raw_links)
            
        if num_loaded == 0:
            return {
                "status": "failed",
                "message": "No valid nodes were loaded."
            }
            
        # Run auto-benchmark on startup if requested to sort the fastest nodes
        benchmarked_count = 0
        if auto_benchmark:
            try:
                logger.info("Running fast startup auto-benchmark on %d nodes...", num_loaded)
                # Cap concurrency to 5 for speed/bandwidth safety during startup
                await _xray_manager.benchmark_all_nodes(test_url=test_url, max_concurrency=5)
                # Count functional nodes
                benchmarked_count = len([n for n in _xray_manager.nodes if n.is_healthy and n.latency > 0])
                logger.info("Startup benchmark complete. Found %d working nodes.", benchmarked_count)
            except Exception as bench_err:
                logger.error("Startup auto-benchmark failed: %s. Continuing with raw nodes list.", bench_err)
            
        # Initialize proxy pool if it does not exist
        if not _proxy_pool:
            _proxy_pool = ProxyPool(
                proxies=[],
                rotation_strategy=RotationStrategy.ROUND_ROBIN,
                xray_manager=_xray_manager
            )
            browser_pool.set_proxy_pool(_proxy_pool)
        else:
            _proxy_pool.xray_manager = _xray_manager
            # Remove any existing xray proxies to prevent duplicates
            _proxy_pool.proxies = [p for p in _proxy_pool.proxies if not p.is_xray]
            
        # Launch Xray clients on designated ports and register in proxy pool
        active_ports = []
        for i in range(num_ports):
            port = start_port + i
            try:
                _xray_manager.start_port(port)
                _proxy_pool.add_xray_proxy(port)
                active_ports.append(port)
            except Exception as port_err:
                logger.error("Failed to start Xray client on port %d: %s", port, port_err)
                
        if not active_ports:
            return {
                "status": "failed",
                "message": "Failed to start Xray on any port."
            }
            
        set_http_proxy_pool(_proxy_pool)
        return {
            "status": "success",
            "message": f"Successfully configured Xray proxy pool with {len(active_ports)} active ports.",
            "loaded_nodes_count": num_loaded,
            "auto_benchmarked": auto_benchmark,
            "working_nodes_count": benchmarked_count if auto_benchmark else num_loaded,
            "active_ports": active_ports,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error configuring Xray subscription: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def handle_get_xray_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_xray_status tool."""
    if not _xray_manager:
        return {
            "status": "inactive",
            "message": "Xray core proxy manager has not been configured yet. Use configure_xray_subscription to start."
        }
        
    try:
        active_clients = []
        for port, runner in _xray_manager.runners.items():
            if runner.process and runner.process.poll() is None:
                active_clients.append({
                    "port": port,
                    "node_name": runner.node.name if runner.node else "Unknown",
                    "protocol": runner.node.protocol if runner.node else "Unknown",
                    "address": runner.node.address if runner.node else "Unknown",
                    "port_remote": runner.node.port if runner.node else 0,
                    "status": "running"
                })
            else:
                active_clients.append({
                    "port": port,
                    "status": "stopped"
                })
                
        all_nodes = [
            {
                "name": node.name,
                "protocol": node.protocol,
                "address": node.address,
                "port": node.port,
                "latency_ms": round(node.latency, 2) if node.latency > 0 else -1,
                "status": "healthy" if node.is_healthy else "unhealthy"
            }
            for node in _xray_manager.nodes
        ]
        
        return {
            "status": "active",
            "binary_path": _xray_manager.binary_path,
            "total_nodes": len(_xray_manager.nodes),
            "active_clients": active_clients,
            "all_nodes": all_nodes,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting Xray status: {e}", exc_info=True)
        raise


async def handle_rotate_xray_node(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle rotate_xray_node tool."""
    port = arguments["port"]
    
    if not _xray_manager:
        return {
            "error": "Xray manager not initialized. Please configure subscription first."
        }
        
    try:
        if port not in _xray_manager.runners:
            return {
                "error": f"No active Xray client found on port {port}"
            }
            
        new_proxy_url = _xray_manager.rotate_node(port)
        
        # Reset failure count in proxy pool
        if _proxy_pool:
            for proxy in _proxy_pool.proxies:
                if proxy.is_xray and proxy.xray_port == port:
                    proxy.mark_success()
                    
        runner = _xray_manager.runners[port]
        return {
            "status": "rotated",
            "port": port,
            "new_proxy_url": new_proxy_url,
            "new_node_name": runner.node.name if runner.node else "Unknown",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error rotating Xray node on port {port}: {e}", exc_info=True)
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def handle_test_xray_nodes(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle test_xray_nodes tool."""
    test_url = arguments.get("test_url", "http://httpbin.org/ip")
    max_concurrency = arguments.get("max_concurrency", 5)
    
    if not _xray_manager:
        return {
            "error": "Xray manager not initialized. Please configure subscription first."
        }
        
    try:
        benchmark_results = await _xray_manager.benchmark_all_nodes(test_url, max_concurrency)
        
        # After testing/sorting, re-register node rotation mapping on active ports so they use the fastest nodes!
        for port in list(_xray_manager.runners.keys()):
            try:
                _xray_manager.start_port(port)
            except Exception as e:
                logger.error(f"Failed to reset port {port} to top healthy node after benchmark: {e}")
                
        return {
            "status": "success",
            "message": "Successfully benchmarked and resorted all Xray nodes by speed.",
            "results": benchmark_results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error benchmarking Xray nodes: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# GraphQL Handlers
# ============================================================================

async def handle_execute_graphql(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle execute_graphql tool."""
    from ..intelligence.network.graphql import GraphQLClient
    
    endpoint = arguments["endpoint"]
    query = arguments["query"]
    variables = arguments.get("variables", {})
    
    try:
        client = GraphQLClient(endpoint)
        result = await client.query(query, variables)
        
        if result:
            return {
                "endpoint": endpoint,
                "status": "success",
                "data": result.get("data"),
                "errors": result.get("errors"),
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "endpoint": endpoint,
                "status": "failed",
                "error": "Query failed or returned no data",
                "timestamp": datetime.now().isoformat(),
            }
    except Exception as e:
        logger.error(f"Error executing GraphQL query: {e}", exc_info=True)
        raise


# ============================================================================
# Page Interaction Handlers
# ============================================================================

@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_execute_js(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle execute_js tool.

    Security: refuses to run unless ``CRAWLEMOON_ALLOW_DANGEROUS_JS=true``.
    Enforces a length cap and per-script timeout (see :class:`MCPServerConfig`).
    """
    url = arguments["url"]
    script = arguments["script"]
    wait_for = arguments.get("wait_for")

    validate_js_payload(
        script,
        field="script",
        max_length=config.js_max_length,
        allow_dangerous=config.allow_dangerous_js,
    )

    await rate_limiter.wait_if_needed(url)

    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)

            if wait_for and wait_for not in ["load", "networkidle"]:
                await page.wait_for_selector(wait_for, timeout=10000)

            result = await asyncio.wait_for(
                page.evaluate(script), timeout=config.js_exec_timeout
            )

            return {
                "url": url,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        except asyncio.TimeoutError:
            logger.error("execute_js timed out after %.1fs on %s", config.js_exec_timeout, url)
            raise TimeoutError(
                f"execute_js exceeded {config.js_exec_timeout}s timeout"
            )
        except Exception as e:
            logger.error(f"Error executing JS on {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_get_cookies(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_cookies tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            cookies = await page.context.cookies()
            
            return {
                "url": url,
                "cookies": [
                    {
                        "name": c.get("name"),
                        "value": c.get("value"),
                        "domain": c.get("domain"),
                        "path": c.get("path"),
                        "expires": c.get("expires"),
                        "httpOnly": c.get("httpOnly"),
                        "secure": c.get("secure"),
                        "sameSite": c.get("sameSite"),
                    }
                    for c in cookies
                ],
                "count": len(cookies),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting cookies from {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_get_storage(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_storage tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            # Get localStorage
            local_storage = await page.evaluate("""
                () => {
                    const items = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        items[key] = localStorage.getItem(key);
                    }
                    return items;
                }
            """)
            
            # Get sessionStorage
            session_storage = await page.evaluate("""
                () => {
                    const items = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        items[key] = sessionStorage.getItem(key);
                    }
                    return items;
                }
            """)
            
            return {
                "url": url,
                "localStorage": local_storage,
                "sessionStorage": session_storage,
                "localStorage_count": len(local_storage),
                "sessionStorage_count": len(session_storage),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting storage from {url}: {e}", exc_info=True)
            raise


# ============================================================================
# Recording Management Handlers
# ============================================================================

async def handle_delete_recording(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle delete_recording tool."""
    recording_id = arguments["recording_id"]
    
    try:
        deleted = recording_storage.delete_recording(recording_id)
        
        return {
            "recording_id": recording_id,
            "status": "deleted" if deleted else "not_found",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error deleting recording {recording_id}: {e}", exc_info=True)
        raise


async def handle_export_recording(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle export_recording tool."""
    recording_id = arguments["recording_id"]
    export_format = arguments.get("format", "json")
    
    try:
        try:
            recording = recording_storage.load_recording(recording_id)
        except (RecordingNotFoundError, RecordingExpiredError) as exc:
            return {
                "error": str(exc),
                "recording_id": recording_id,
            }

        if export_format == "json":
            # Return recording as JSON
            output = {
                "id": recording.id,
                "start_time": recording.start_time.isoformat() if recording.start_time else None,
                "end_time": recording.end_time.isoformat() if recording.end_time else None,
                "duration": recording.duration,
                "events": [
                    {
                        "type": e.type.value,
                        "timestamp": e.timestamp,
                        "data": e.data,
                    }
                    for e in recording.events
                ],
                "network": [
                    {
                        "url": n.url,
                        "method": n.method,
                        "status": n.status,
                    }
                    for n in recording.network
                ] if hasattr(recording, 'network') else [],
            }
        elif export_format == "har":
            # Export as HAR format
            output = {
                "log": {
                    "version": "1.2",
                    "creator": {"name": "Crawlemoon", "version": "1.0"},
                    "entries": [
                        {
                            "request": {
                                "method": n.method,
                                "url": n.url,
                            },
                            "response": {
                                "status": n.status,
                            },
                        }
                        for n in (recording.network if hasattr(recording, 'network') else [])
                    ],
                }
            }
        elif export_format == "playwright_test":
            # Generate Playwright test
            generator = CrawlerGenerator()
            crawler_def = generator.from_recording(recording)
            output = generator.to_playwright_script(crawler_def)
        else:
            output = None
        
        return {
            "recording_id": recording_id,
            "format": export_format,
            "output": output,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error exporting recording {recording_id}: {e}", exc_info=True)
        raise


# ============================================================================
# Content Extraction Handlers
# ============================================================================

@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_extract_links(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_links tool."""
    url = arguments["url"]
    filter_internal = arguments.get("filter_internal", False)
    filter_external = arguments.get("filter_external", False)
    include_text = arguments.get("include_text", True)
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            from urllib.parse import urlparse
            base_domain = urlparse(url).netloc
            
            links = await page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        links.push({
                            href: a.href,
                            text: a.textContent.trim(),
                            title: a.title || null,
                            rel: a.rel || null,
                        });
                    });
                    return links;
                }
            """)
            
            # Filter links
            filtered_links = []
            for link in links:
                link_domain = urlparse(link.get("href", "")).netloc
                is_internal = link_domain == base_domain or link_domain == ""
                
                if filter_internal and not is_internal:
                    continue
                if filter_external and is_internal:
                    continue
                
                if include_text:
                    filtered_links.append(link)
                else:
                    filtered_links.append({"href": link.get("href")})
            
            return {
                "url": url,
                "links": filtered_links,
                "total": len(filtered_links),
                "internal_filter": filter_internal,
                "external_filter": filter_external,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error extracting links from {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_extract_forms(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_forms tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            forms = await page.evaluate("""
                () => {
                    const forms = [];
                    document.querySelectorAll('form').forEach((form, idx) => {
                        const fields = [];
                        form.querySelectorAll('input, select, textarea').forEach(field => {
                            fields.push({
                                tag: field.tagName.toLowerCase(),
                                type: field.type || null,
                                name: field.name || null,
                                id: field.id || null,
                                placeholder: field.placeholder || null,
                                required: field.required || false,
                                value: field.type === 'password' ? '***' : (field.value || null),
                            });
                        });
                        
                        forms.push({
                            index: idx,
                            action: form.action || null,
                            method: form.method || 'GET',
                            id: form.id || null,
                            name: form.name || null,
                            enctype: form.enctype || null,
                            fields: fields,
                        });
                    });
                    return forms;
                }
            """)
            
            return {
                "url": url,
                "forms": forms,
                "total": len(forms),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error extracting forms from {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_extract_metadata(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_metadata tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            metadata = await page.evaluate("""
                () => {
                    const result = {
                        title: document.title,
                        description: null,
                        canonical: null,
                        og: {},
                        twitter: {},
                        meta: {},
                        jsonLd: [],
                    };
                    
                    // Meta tags
                    document.querySelectorAll('meta').forEach(meta => {
                        const name = meta.getAttribute('name') || meta.getAttribute('property');
                        const content = meta.getAttribute('content');
                        
                        if (name && content) {
                            if (name.startsWith('og:')) {
                                result.og[name.replace('og:', '')] = content;
                            } else if (name.startsWith('twitter:')) {
                                result.twitter[name.replace('twitter:', '')] = content;
                            } else {
                                result.meta[name] = content;
                            }
                            
                            if (name === 'description') {
                                result.description = content;
                            }
                        }
                    });
                    
                    // Canonical URL
                    const canonical = document.querySelector('link[rel="canonical"]');
                    if (canonical) {
                        result.canonical = canonical.href;
                    }
                    
                    // JSON-LD structured data
                    document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
                        try {
                            result.jsonLd.push(JSON.parse(script.textContent));
                        } catch (e) {}
                    });
                    
                    return result;
                }
            """)
            
            return {
                "url": url,
                **metadata,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error extracting metadata from {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_extract_tables(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_tables tool."""
    url = arguments["url"]
    output_format = arguments.get("format", "json")
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            tables = await page.evaluate("""
                () => {
                    const tables = [];
                    document.querySelectorAll('table').forEach((table, idx) => {
                        const headers = [];
                        const rows = [];
                        
                        // Get headers
                        table.querySelectorAll('thead th, thead td, tr:first-child th').forEach(th => {
                            headers.push(th.textContent.trim());
                        });
                        
                        // Get rows
                        table.querySelectorAll('tbody tr, tr').forEach((tr, rowIdx) => {
                            // Skip header row if we already got headers
                            if (rowIdx === 0 && headers.length > 0) return;
                            
                            const cells = [];
                            tr.querySelectorAll('td, th').forEach(td => {
                                cells.push(td.textContent.trim());
                            });
                            if (cells.length > 0) {
                                rows.push(cells);
                            }
                        });
                        
                        tables.push({
                            index: idx,
                            id: table.id || null,
                            headers: headers,
                            rows: rows,
                            rowCount: rows.length,
                            colCount: headers.length || (rows[0] ? rows[0].length : 0),
                        });
                    });
                    return tables;
                }
            """)
            
            # Convert to requested format
            if output_format == "csv":
                csv_tables = []
                for table in tables:
                    csv_rows = []
                    if table["headers"]:
                        csv_rows.append(",".join(f'"{h}"' for h in table["headers"]))
                    for row in table["rows"]:
                        csv_rows.append(",".join(f'"{c}"' for c in row))
                    csv_tables.append("\n".join(csv_rows))
                output = csv_tables
            elif output_format == "markdown":
                md_tables = []
                for table in tables:
                    md_rows = []
                    if table["headers"]:
                        md_rows.append("| " + " | ".join(table["headers"]) + " |")
                        md_rows.append("| " + " | ".join(["---"] * len(table["headers"])) + " |")
                    for row in table["rows"]:
                        md_rows.append("| " + " | ".join(row) + " |")
                    md_tables.append("\n".join(md_rows))
                output = md_tables
            else:
                output = tables
            
            return {
                "url": url,
                "tables": output,
                "total": len(tables),
                "format": output_format,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error extracting tables from {url}: {e}", exc_info=True)
            raise


# ============================================================================
# CDP Handlers
# ============================================================================

@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_execute_cdp(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle execute_cdp tool.

    Security: refuses to run unless ``CRAWLEMOON_ALLOW_DANGEROUS_JS=true`` because
    CDP exposes Runtime.evaluate, Page.addScriptToEvaluateOnNewDocument, etc.
    """
    url = arguments["url"]
    method = arguments["method"]
    params = arguments.get("params", {})

    if not config.allow_dangerous_js:
        raise ValidationError(
            "execute_cdp is disabled. Set CRAWLEMOON_ALLOW_DANGEROUS_JS=true to enable."
        )
    if not isinstance(method, str) or not method:
        raise ValidationError("'method' must be a non-empty CDP method name")

    await rate_limiter.wait_if_needed(url)
    
    context = None
    page = None
    try:
        context = await create_stealth_context(browser_pool, url=url)
        page = await context.new_page()
        page.set_default_timeout(config.navigation_timeout * 1000)
        await apply_stealth_to_page(context, page)
        
        response = await navigate_to_url(page, url)
        
        # Create CDP client
        cdp_client = CDPClient(context)
        await cdp_client.connect()
        
        # Execute CDP command
        result = await cdp_client.send_command(method, params)
        
        return {
            "url": url,
            "method": method,
            "params": params,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error executing CDP command on {url}: {e}", exc_info=True)
        raise
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        # Don't close context - let pool manage its lifecycle


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_get_dom_tree(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_dom_tree tool."""
    url = arguments["url"]
    depth = arguments.get("depth", -1)
    
    await rate_limiter.wait_if_needed(url)
    
    context = None
    page = None
    try:
        context = await create_stealth_context(browser_pool, url=url)
        page = await context.new_page()
        page.set_default_timeout(config.navigation_timeout * 1000)
        await apply_stealth_to_page(context, page)
        
        response = await navigate_to_url(page, url)
        
        # Create CDP client
        cdp_client = CDPClient(context)
        await cdp_client.connect()
        
        # Get DOM tree
        dom_tree = await cdp_client.get_dom_tree(depth)
        
        return {
            "url": url,
            "depth": depth,
            "dom": dom_tree,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting DOM tree from {url}: {e}", exc_info=True)
        raise
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        # Don't close context - let pool manage its lifecycle


# ============================================================================
# Performance and Analysis Handlers
# ============================================================================

@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_measure_performance(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle measure_performance tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            # Navigate and get performance timing
            response = await page.goto(url, wait_until="networkidle", timeout=config.navigation_timeout * 1000)
            
            if response:
                rate_limiter.record_response(url, response.status)
            
            # Get performance metrics
            metrics = await page.evaluate("""
                () => {
                    const timing = performance.timing;
                    const navigation = performance.getEntriesByType('navigation')[0] || {};
                    
                    return {
                        // Navigation timing
                        dns: timing.domainLookupEnd - timing.domainLookupStart,
                        tcp: timing.connectEnd - timing.connectStart,
                        ssl: timing.connectEnd - timing.secureConnectionStart,
                        ttfb: timing.responseStart - timing.requestStart,
                        download: timing.responseEnd - timing.responseStart,
                        domInteractive: timing.domInteractive - timing.navigationStart,
                        domComplete: timing.domComplete - timing.navigationStart,
                        loadEvent: timing.loadEventEnd - timing.navigationStart,
                        
                        // Navigation entry metrics
                        transferSize: navigation.transferSize || 0,
                        encodedBodySize: navigation.encodedBodySize || 0,
                        decodedBodySize: navigation.decodedBodySize || 0,
                        
                        // Resource counts
                        resourceCount: performance.getEntriesByType('resource').length,
                    };
                }
            """)
            
            # Get Core Web Vitals (if available)
            web_vitals = await page.evaluate("""
                () => {
                    return new Promise(resolve => {
                        const vitals = {
                            lcp: null,
                            fid: null,
                            cls: null,
                        };
                        
                        // LCP
                        new PerformanceObserver(list => {
                            const entries = list.getEntries();
                            if (entries.length > 0) {
                                vitals.lcp = entries[entries.length - 1].startTime;
                            }
                        }).observe({ type: 'largest-contentful-paint', buffered: true });
                        
                        // CLS
                        let clsValue = 0;
                        new PerformanceObserver(list => {
                            for (const entry of list.getEntries()) {
                                if (!entry.hadRecentInput) {
                                    clsValue += entry.value;
                                }
                            }
                            vitals.cls = clsValue;
                        }).observe({ type: 'layout-shift', buffered: true });
                        
                        // Resolve after a short delay
                        setTimeout(() => resolve(vitals), 100);
                    });
                }
            """)
            
            return {
                "url": url,
                "timing": metrics,
                "webVitals": web_vitals,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error measuring performance for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_analyze_resources(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_resources tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            resources = await page.evaluate("""
                () => {
                    const entries = performance.getEntriesByType('resource');
                    const byType = {};
                    const resources = [];
                    
                    entries.forEach(entry => {
                        const type = entry.initiatorType || 'other';
                        byType[type] = (byType[type] || 0) + 1;
                        
                        resources.push({
                            url: entry.name,
                            type: type,
                            duration: entry.duration,
                            transferSize: entry.transferSize || 0,
                            encodedBodySize: entry.encodedBodySize || 0,
                            decodedBodySize: entry.decodedBodySize || 0,
                        });
                    });
                    
                    return {
                        total: entries.length,
                        byType: byType,
                        totalSize: resources.reduce((sum, r) => sum + r.transferSize, 0),
                        resources: resources.slice(0, 100), // Limit to first 100
                    };
                }
            """)
            
            return {
                "url": url,
                **resources,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error analyzing resources for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_check_accessibility(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle check_accessibility tool."""
    url = arguments["url"]
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            # Basic accessibility checks
            issues = await page.evaluate("""
                () => {
                    const issues = [];
                    
                    // Check images without alt
                    document.querySelectorAll('img:not([alt])').forEach(img => {
                        issues.push({
                            type: 'missing_alt',
                            severity: 'error',
                            element: 'img',
                            description: 'Image missing alt attribute',
                            selector: img.id ? `#${img.id}` : (img.className ? `.${img.className.split(' ')[0]}` : 'img'),
                        });
                    });
                    
                    // Check form inputs without labels
                    document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"])').forEach(input => {
                        const id = input.id;
                        const hasLabel = id && document.querySelector(`label[for="${id}"]`);
                        const hasAriaLabel = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');
                        
                        if (!hasLabel && !hasAriaLabel) {
                            issues.push({
                                type: 'missing_label',
                                severity: 'error',
                                element: 'input',
                                description: 'Input missing associated label',
                                selector: input.id ? `#${input.id}` : (input.name ? `input[name="${input.name}"]` : 'input'),
                            });
                        }
                    });
                    
                    // Check empty links
                    document.querySelectorAll('a').forEach(link => {
                        const text = link.textContent.trim();
                        const hasAriaLabel = link.hasAttribute('aria-label');
                        const hasImage = link.querySelector('img[alt]');
                        
                        if (!text && !hasAriaLabel && !hasImage) {
                            issues.push({
                                type: 'empty_link',
                                severity: 'error',
                                element: 'a',
                                description: 'Link has no accessible text',
                                selector: link.href ? `a[href="${link.getAttribute('href')}"]` : 'a',
                            });
                        }
                    });
                    
                    // Check heading hierarchy
                    const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
                    let lastLevel = 0;
                    headings.forEach(h => {
                        const level = parseInt(h.tagName[1]);
                        if (level > lastLevel + 1) {
                            issues.push({
                                type: 'heading_skip',
                                severity: 'warning',
                                element: h.tagName.toLowerCase(),
                                description: `Heading level skipped (from h${lastLevel} to h${level})`,
                                selector: h.id ? `#${h.id}` : h.tagName.toLowerCase(),
                            });
                        }
                        lastLevel = level;
                    });
                    
                    // Check color contrast (basic check)
                    document.querySelectorAll('*').forEach(el => {
                        const style = window.getComputedStyle(el);
                        const color = style.color;
                        const bg = style.backgroundColor;
                        // Simple check for very low contrast
                        if (color === bg && color !== 'rgba(0, 0, 0, 0)') {
                            issues.push({
                                type: 'low_contrast',
                                severity: 'warning',
                                element: el.tagName.toLowerCase(),
                                description: 'Possible low color contrast',
                            });
                        }
                    });
                    
                    return {
                        issues: issues,
                        counts: {
                            errors: issues.filter(i => i.severity === 'error').length,
                            warnings: issues.filter(i => i.severity === 'warning').length,
                        },
                        checks: ['alt_text', 'form_labels', 'empty_links', 'heading_hierarchy', 'color_contrast'],
                    };
                }
            """)
            
            return {
                "url": url,
                **issues,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error checking accessibility for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_compare_pages(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle compare_pages tool."""
    url1 = arguments["url1"]
    url2 = arguments["url2"]
    compare_type = arguments.get("compare_type", "both")
    
    await rate_limiter.wait_if_needed(url1)
    await rate_limiter.wait_if_needed(url2)
    
    async with browser_context_manager(url=url1) as page1:
        async with browser_context_manager(url=url2) as page2:
            try:
                wait_until = "networkidle" if config.wait_for_network_idle else "load"
                
                # Navigate to both pages
                response1 = await page1.goto(url1, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
                response2 = await page2.goto(url2, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
                
                if response1:
                    rate_limiter.record_response(url1, response1.status)
                if response2:
                    rate_limiter.record_response(url2, response2.status)
                
                result = {
                    "url1": url1,
                    "url2": url2,
                    "compare_type": compare_type,
                }
                
                if compare_type in ["structure", "both"]:
                    # Compare DOM structure
                    structure1 = await page1.evaluate("""
                        () => {
                            const countElements = (el) => {
                                const counts = {};
                                const walk = (node) => {
                                    if (node.nodeType === 1) {
                                        const tag = node.tagName.toLowerCase();
                                        counts[tag] = (counts[tag] || 0) + 1;
                                        Array.from(node.children).forEach(walk);
                                    }
                                };
                                walk(el);
                                return counts;
                            };
                            return {
                                elements: countElements(document.body),
                                totalElements: document.body.getElementsByTagName('*').length,
                            };
                        }
                    """)
                    
                    structure2 = await page2.evaluate("""
                        () => {
                            const countElements = (el) => {
                                const counts = {};
                                const walk = (node) => {
                                    if (node.nodeType === 1) {
                                        const tag = node.tagName.toLowerCase();
                                        counts[tag] = (counts[tag] || 0) + 1;
                                        Array.from(node.children).forEach(walk);
                                    }
                                };
                                walk(el);
                                return counts;
                            };
                            return {
                                elements: countElements(document.body),
                                totalElements: document.body.getElementsByTagName('*').length,
                            };
                        }
                    """)
                    
                    # Find differences
                    all_tags = set(structure1["elements"].keys()) | set(structure2["elements"].keys())
                    element_diffs = {}
                    for tag in all_tags:
                        count1 = structure1["elements"].get(tag, 0)
                        count2 = structure2["elements"].get(tag, 0)
                        if count1 != count2:
                            element_diffs[tag] = {"url1": count1, "url2": count2, "diff": count2 - count1}
                    
                    result["structure"] = {
                        "url1_elements": structure1["totalElements"],
                        "url2_elements": structure2["totalElements"],
                        "element_differences": element_diffs,
                    }
                
                if compare_type in ["content", "both"]:
                    # Compare text content
                    text1 = await page1.evaluate("() => document.body.innerText")
                    text2 = await page2.evaluate("() => document.body.innerText")
                    
                    # Simple word comparison
                    words1 = set(text1.lower().split())
                    words2 = set(text2.lower().split())
                    
                    result["content"] = {
                        "url1_word_count": len(words1),
                        "url2_word_count": len(words2),
                        "common_words": len(words1 & words2),
                        "unique_to_url1": len(words1 - words2),
                        "unique_to_url2": len(words2 - words1),
                        "similarity": len(words1 & words2) / len(words1 | words2) if words1 | words2 else 0,
                    }
                
                result["timestamp"] = datetime.now().isoformat()
                return result
                
            except Exception as e:
                logger.error(f"Error comparing pages: {e}", exc_info=True)
                raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_monitor_network(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle monitor_network tool."""
    url = arguments["url"]
    duration = arguments.get("duration", 10)
    filter_type = arguments.get("filter_type", "all")
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            requests_data = []
            
            # Set up request listener
            async def on_request(request):
                req_type = request.resource_type
                if filter_type == "all" or req_type == filter_type:
                    requests_data.append({
                        "url": request.url,
                        "method": request.method,
                        "type": req_type,
                        "headers": dict(request.headers),
                        "timestamp": datetime.now().isoformat(),
                    })
            
            async def on_response(response):
                # Update request with response info
                for req in requests_data:
                    if req["url"] == response.url:
                        req["status"] = response.status
                        req["response_headers"] = dict(response.headers)
                        break
            
            page.on("request", on_request)
            page.on("response", on_response)
            
            # Navigate
            wait_until = "load"  # Don't wait for networkidle when monitoring
            response = await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
            
            if response:
                rate_limiter.record_response(url, response.status)
            
            # Monitor for specified duration
            await asyncio.sleep(duration)
            
            return {
                "url": url,
                "duration": duration,
                "filter_type": filter_type,
                "requests": requests_data,
                "total": len(requests_data),
                "by_type": {t: sum(1 for r in requests_data if r.get("type") == t) for t in {r.get("type") for r in requests_data}},
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error monitoring network for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_fill_form(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fill_form tool."""
    url = arguments["url"]
    form_selector = arguments.get("form_selector")
    data = arguments["data"]
    submit = arguments.get("submit", False)
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            response = await navigate_to_url(page, url)
            
            filled_fields = []
            
            # Fill form fields
            for field_name, value in data.items():
                try:
                    # Try multiple selector strategies
                    selectors = [
                        f'input[name="{field_name}"]',
                        f'input[id="{field_name}"]',
                        f'textarea[name="{field_name}"]',
                        f'textarea[id="{field_name}"]',
                        f'select[name="{field_name}"]',
                        f'select[id="{field_name}"]',
                    ]
                    
                    if form_selector:
                        selectors = [f'{form_selector} {s}' for s in selectors]
                    
                    for selector in selectors:
                        try:
                            element = await page.query_selector(selector)
                            if element:
                                tag = await element.evaluate("el => el.tagName.toLowerCase()")
                                
                                if tag == "select":
                                    await element.select_option(value)
                                else:
                                    await element.fill(str(value))
                                
                                filled_fields.append({"name": field_name, "selector": selector, "value": value})
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"Could not fill field {field_name}: {e}")
            
            result = {
                "url": url,
                "filled_fields": filled_fields,
                "total_filled": len(filled_fields),
                "total_requested": len(data),
                "submitted": False,
            }
            
            # Submit if requested
            if submit and filled_fields:
                try:
                    submit_selector = f'{form_selector} [type="submit"], {form_selector} button' if form_selector else '[type="submit"], button'
                    submit_button = await page.query_selector(submit_selector)
                    
                    if submit_button:
                        await submit_button.click()
                        await page.wait_for_load_state("networkidle")
                        result["submitted"] = True
                        result["final_url"] = page.url
                except Exception as e:
                    result["submit_error"] = str(e)
            
            result["timestamp"] = datetime.now().isoformat()
            return result
            
        except Exception as e:
            logger.error(f"Error filling form on {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_wait_and_extract(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle wait_and_extract tool."""
    url = arguments["url"]
    selector = arguments["selector"]
    timeout = arguments.get("timeout", 30)
    extract_type = arguments.get("extract_type", "text")
    attribute = arguments.get("attribute")
    
    await rate_limiter.wait_if_needed(url)
    
    async with browser_context_manager(url=url) as page:
        try:
            # Navigate
            response = await page.goto(url, wait_until="load", timeout=config.navigation_timeout * 1000)
            
            if response:
                rate_limiter.record_response(url, response.status)
            
            # Wait for selector
            await page.wait_for_selector(selector, timeout=timeout * 1000)
            
            # Extract content
            elements = await page.query_selector_all(selector)
            
            extracted = []
            for element in elements:
                try:
                    if extract_type == "text":
                        content = await element.inner_text()
                    elif extract_type == "html":
                        content = await element.inner_html()
                    elif extract_type == "attribute" and attribute:
                        content = await element.get_attribute(attribute)
                    else:
                        content = await element.inner_text()
                    
                    extracted.append(content)
                except Exception as e:
                    logger.warning(f"Error extracting from element: {e}")
            
            return {
                "url": url,
                "selector": selector,
                "extract_type": extract_type,
                "attribute": attribute,
                "content": extracted[0] if len(extracted) == 1 else extracted,
                "count": len(extracted),
                "timestamp": datetime.now().isoformat(),
            }
        except asyncio.TimeoutError:
            return {
                "url": url,
                "selector": selector,
                "error": f"Timeout waiting for selector after {timeout} seconds",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error in wait_and_extract for {url}: {e}", exc_info=True)
            raise


async def main():
    """Main entry point for MCP server."""
    await init_browser_pool()
    try:
        await cache_manager.start_sweeper(interval_seconds=60.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not start cache sweeper: %s", exc)

    from mcp.server.stdio import stdio_server
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Cleanup on shutdown
        await browser_pool.close()
        logger.info("MCP server shutdown complete")


def main_sync():
    """Synchronous entry point for CLI/uvx."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
