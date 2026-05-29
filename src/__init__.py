"""Crawlify - Advanced Web Crawling Platform."""

__version__ = "1.1.5"

# Re-export the exception hierarchy so callers can use ``from src import CrawlifyError``
from .exceptions import (  # noqa: F401
    CrawlifyError,
    BrowserError,
    BrowserPoolError,
    BrowserPoolExhaustedError,
    BrowserInitError,
    PageNavigationError,
    PageInteractionError,
    ProxyError,
    NoHealthyProxyError,
    ProxyTestError,
    NetworkError,
    HTTPRequestError,
    RateLimitError,
    ConnectionPoolError,
    CacheError,
    CacheBackendError,
    CacheSerializationError,
    SessionError,
    SessionNotFoundError,
    SessionEncryptionError,
    SessionStorageError,
    RecordingError,
    RecordingNotFoundError,
    RecordingSerializationError,
    RecordingExpiredError,
    AnalysisError,
    APIDiscoveryError,
    GraphQLError,
    JSAnalysisError,
    SitemapError,
    BotDetectionError,
    CaptchaError,
    TechnologyDetectionError,
    ContentExtractionError,
    CrawlerGenerationError,
    ConfigurationError,
    ValidationError,
    URLValidationError,
)


