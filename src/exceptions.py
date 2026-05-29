"""Custom exception hierarchy for Crawlify MCP Server.

All application-specific exceptions derive from CrawlifyError, allowing
callers to catch the entire family with a single except clause while still
being able to target narrower sub-types when needed.
"""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class CrawlifyError(Exception):
    """Root exception for all Crawlify errors."""


# ---------------------------------------------------------------------------
# Browser / Pool
# ---------------------------------------------------------------------------

class BrowserError(CrawlifyError):
    """Base class for browser-related errors."""


class BrowserPoolError(BrowserError):
    """Browser pool is exhausted, unavailable, or misconfigured."""


class BrowserPoolExhaustedError(BrowserPoolError):
    """No browser slot became available within the timeout window."""


class BrowserInitError(BrowserError):
    """Playwright or browser binary could not be initialised."""


class PageNavigationError(BrowserError):
    """A page navigation failed (timeout, crash, bad URL, etc.)."""


class PageInteractionError(BrowserError):
    """A page interaction (click, fill, etc.) failed."""


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------

class ProxyError(CrawlifyError):
    """Base class for proxy-related errors."""


class NoHealthyProxyError(ProxyError):
    """All proxies in the pool are unhealthy or missing."""


class ProxyTestError(ProxyError):
    """A proxy connectivity test failed."""


# ---------------------------------------------------------------------------
# Network / HTTP
# ---------------------------------------------------------------------------

class NetworkError(CrawlifyError):
    """Base class for network-level errors."""


class HTTPRequestError(NetworkError):
    """An outbound HTTP request failed."""


class RateLimitError(NetworkError):
    """A rate-limit (429 / 503) response was received from the target."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


class ConnectionPoolError(NetworkError):
    """HTTP connection pool could not satisfy the request."""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class CacheError(CrawlifyError):
    """Base class for cache-related errors."""


class CacheBackendError(CacheError):
    """The cache backend (Redis, Memcached, etc.) is unreachable."""


class CacheSerializationError(CacheError):
    """An object could not be serialised/deserialised for the cache."""


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionError(CrawlifyError):
    """Base class for session-related errors."""


class SessionNotFoundError(SessionError):
    """The requested session does not exist."""


class SessionEncryptionError(SessionError):
    """Session data could not be encrypted or decrypted."""


class SessionStorageError(SessionError):
    """Session data could not be persisted or loaded."""


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

class RecordingError(CrawlifyError):
    """Base class for session-recording errors."""


class RecordingNotFoundError(RecordingError):
    """The requested recording does not exist."""


class RecordingSerializationError(RecordingError):
    """A recording could not be serialised or deserialised."""


class RecordingExpiredError(RecordingError):
    """A recording exceeded its retention window and has been deleted."""


# ---------------------------------------------------------------------------
# Intelligence / Analysis
# ---------------------------------------------------------------------------

class AnalysisError(CrawlifyError):
    """Base class for intelligence / analysis errors."""


class APIDiscoveryError(AnalysisError):
    """API discovery failed for the target URL."""


class GraphQLError(AnalysisError):
    """A GraphQL introspection or query operation failed."""


class JSAnalysisError(AnalysisError):
    """JavaScript analysis or deobfuscation failed."""


class SitemapError(AnalysisError):
    """Sitemap fetching or parsing failed."""


class BotDetectionError(AnalysisError):
    """Bot-detection analysis encountered an error."""


class CaptchaError(AnalysisError):
    """CAPTCHA solving failed or timed out."""


class TechnologyDetectionError(AnalysisError):
    """Technology-stack detection encountered an error."""


class ContentExtractionError(AnalysisError):
    """Content extraction (article, smart, etc.) failed."""


# ---------------------------------------------------------------------------
# Crawler generation
# ---------------------------------------------------------------------------

class CrawlerGenerationError(CrawlifyError):
    """Crawler code or YAML could not be generated."""


# ---------------------------------------------------------------------------
# Configuration / Validation
# ---------------------------------------------------------------------------

class ConfigurationError(CrawlifyError):
    """The server configuration is invalid or incomplete."""


class ValidationError(CrawlifyError):
    """A tool argument or user-supplied value failed validation."""


class URLValidationError(ValidationError):
    """The supplied URL is malformed or uses an unsupported scheme."""
