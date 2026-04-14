"""Crawilfy - Advanced Web Crawling Platform."""

__version__ = "0.1.2"

# Re-export the exception hierarchy so callers can use ``from src import CrawilfyError``
from .exceptions import (  # noqa: F401
    CrawilfyError,
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


