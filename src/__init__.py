"""Crawlemoon - Advanced Web Crawling Platform."""

__version__ = "1.1.9"

# Re-export the exception hierarchy so callers can use ``from src import CrawlemoonError``
from .exceptions import (  # noqa: F401
    CrawlemoonError,
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


