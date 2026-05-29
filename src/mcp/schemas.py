"""Pydantic models for MCP tool argument validation.

Each model corresponds to one or more MCP tools and provides:
- Type coercion from the raw dict that MCP passes in
- Field-level validation with clear error messages
- Default values documented in one place

Usage::

    from src.mcp.schemas import DeepAnalyzeArgs
    args = DeepAnalyzeArgs(**raw_arguments)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # Provide a no-op fallback so the rest of the codebase can still import this
    # module without crashing when pydantic is not installed.
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def Field(*args, **kwargs):  # type: ignore[misc]
        return kwargs.get("default", None)

    def field_validator(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def model_validator(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator


_SAFE_SCHEMES = {"http", "https"}


def _validate_url(v: str) -> str:
    parsed = urlparse(v)
    if parsed.scheme not in _SAFE_SCHEMES or not parsed.netloc:
        raise ValueError(f"URL must use http or https scheme and have a valid host. Got: {v!r}")
    return v


def _validate_positive_int(v: Optional[int], name: str = "value") -> Optional[int]:
    if v is not None and v <= 0:
        raise ValueError(f"{name} must be a positive integer, got {v}")
    return v


# ---------------------------------------------------------------------------
# Shared mixins
# ---------------------------------------------------------------------------

class _URLMixin(BaseModel):
    url: str = Field(..., description="Target URL (must be http or https)")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _validate_url(v)


class _DOMFilterMixin(BaseModel):
    css_selector: Optional[str] = Field(None, description="CSS selector to target specific container for extraction")
    exclude_selectors: Optional[List[str]] = Field(None, description="List of CSS selectors to exclude/remove from the DOM before extraction")

    @field_validator("exclude_selectors", mode="before")
    @classmethod
    def parse_exclude_selectors(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


# ---------------------------------------------------------------------------
# Deep analysis
# ---------------------------------------------------------------------------

class DeepAnalyzeArgs(_URLMixin):
    depth: Literal["basic", "full"] = Field("full", description="Analysis depth")


# ---------------------------------------------------------------------------
# API discovery
# ---------------------------------------------------------------------------

class DiscoverAPIsArgs(_URLMixin):
    include_hidden: bool = Field(True, description="Include undocumented endpoints")


# ---------------------------------------------------------------------------
# GraphQL
# ---------------------------------------------------------------------------

class IntrospectGraphQLArgs(BaseModel):
    endpoint: str = Field(..., description="GraphQL endpoint URL")

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        return _validate_url(v)


class ExecuteGraphQLArgs(_URLMixin):
    query: str = Field(..., description="GraphQL query or mutation string")
    variables: Optional[Dict[str, Any]] = Field(None, description="Optional query variables")
    headers: Optional[Dict[str, str]] = Field(None, description="Optional extra headers")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("GraphQL query must not be empty")
        return v


# ---------------------------------------------------------------------------
# Screenshots / navigation
# ---------------------------------------------------------------------------

class TakeScreenshotArgs(_URLMixin):
    full_page: bool = Field(True, description="Capture the full scrollable page")
    format: Literal["png", "jpeg"] = Field("png", description="Image format")
    quality: int = Field(90, ge=1, le=100, description="JPEG quality (1–100)")


class ExecuteJSArgs(_URLMixin):
    script: str = Field(..., description="JavaScript to execute in the page context")

    @field_validator("script")
    @classmethod
    def validate_script(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("JavaScript script must not be empty")
        return v


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

class ExtractArticleArgs(_URLMixin):
    pass


class ExtractLinksArgs(_URLMixin):
    filter_external: bool = Field(False, description="Exclude links to other domains")
    filter_internal: bool = Field(False, description="Exclude links within the same domain")


class ExtractFormsArgs(_URLMixin):
    pass


class ExtractTablesArgs(_URLMixin):
    pass


class ExtractMetadataArgs(_URLMixin):
    pass


class ConvertToMarkdownArgs(_URLMixin, _DOMFilterMixin):
    pass


class SmartExtractArgs(_URLMixin, _DOMFilterMixin):
    query: str = Field(..., description="Natural-language extraction query")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Extraction query must not be empty")
        return v


class WaitAndExtractArgs(_URLMixin):
    wait_for: str = Field(..., description="CSS selector or JavaScript expression to wait for")
    timeout: int = Field(30, ge=1, le=300, description="Maximum wait in seconds (1–300)")


# ---------------------------------------------------------------------------
# Network analysis
# ---------------------------------------------------------------------------

class AnalyzeSitemapArgs(BaseModel):
    sitemap_url: str = Field(..., description="Sitemap XML URL")

    @field_validator("sitemap_url")
    @classmethod
    def validate_sitemap_url(cls, v: str) -> str:
        return _validate_url(v)


class CheckRobotsArgs(_URLMixin):
    pass


class MonitorNetworkArgs(_URLMixin):
    duration: int = Field(10, ge=1, le=120, description="Monitoring duration in seconds (1–120)")


class AnalyzeWebSocketArgs(_URLMixin):
    pass


# ---------------------------------------------------------------------------
# Security / detection
# ---------------------------------------------------------------------------

class DetectProtectionArgs(_URLMixin):
    pass


class DetectTechnologyArgs(_URLMixin):
    pass


class AnalyzeAuthArgs(_URLMixin):
    pass


class CheckAccessibilityArgs(_URLMixin):
    pass


# ---------------------------------------------------------------------------
# Page interaction
# ---------------------------------------------------------------------------

class FillFormArgs(_URLMixin):
    data: Dict[str, str] = Field(..., description="Mapping of field name/id -> value")
    form_selector: Optional[str] = Field(None, description="Optional CSS selector for the target form")
    submit: bool = Field(False, description="Submit the form after filling")


class GetCookiesArgs(_URLMixin):
    pass


class GetStorageArgs(_URLMixin):
    pass


class GetDOMTreeArgs(_URLMixin):
    depth: int = Field(3, ge=1, le=20, description="DOM tree depth (1–20)")


class MeasurePerformanceArgs(_URLMixin):
    pass


class AnalyzeResourcesArgs(_URLMixin):
    pass


class ComparePagesArgs(BaseModel):
    url1: str = Field(..., description="First page URL")
    url2: str = Field(..., description="Second page URL")

    @field_validator("url1", "url2")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        return _validate_url(v)


# ---------------------------------------------------------------------------
# JavaScript analysis
# ---------------------------------------------------------------------------

class DeobfuscateJSArgs(BaseModel):
    code: str = Field(..., description="JavaScript code to deobfuscate")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("JavaScript code must not be empty")
        return v


class ExtractFromJSArgs(BaseModel):
    code: str = Field(..., description="JavaScript code to analyze")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("JavaScript code must not be empty")
        return v


# ---------------------------------------------------------------------------
# CAPTCHA / stealth
# ---------------------------------------------------------------------------

class SolveCaptchaArgs(_URLMixin):
    captcha_type: Optional[Literal["auto", "recaptcha_v2", "recaptcha", "hcaptcha", "turnstile"]] = Field(
        "auto", description="CAPTCHA type; auto-detected when omitted"
    )


class StealthRequestArgs(_URLMixin):
    browser: Literal["chrome", "edge", "safari", "firefox"] = Field(
        "chrome", description="Browser to impersonate"
    )
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"] = Field("GET")
    headers: Optional[Dict[str, str]] = Field(None)
    body: Optional[str] = Field(None, description="Request body for POST/PUT")


# ---------------------------------------------------------------------------
# Proxy management
# ---------------------------------------------------------------------------

class AddProxyArgs(BaseModel):
    proxy_url: str = Field(..., description="Proxy URL (http/https/socks4/socks5)")
    username: Optional[str] = Field(None)
    password: Optional[str] = Field(None)


class RemoveProxyArgs(BaseModel):
    proxy_url: str = Field(..., description="URL of proxy to remove")


class TestProxyArgs(BaseModel):
    proxy_url: str = Field(..., description="Proxy URL to test")
    test_url: str = Field("http://httpbin.org/ip", description="URL to use for connectivity test")

    @field_validator("test_url")
    @classmethod
    def validate_test_url(cls, v: str) -> str:
        return _validate_url(v)


class ConfigureProxiesArgs(BaseModel):
    proxies: List[str] = Field(..., description="List of proxy URLs to configure")
    rotation_strategy: Literal["round_robin", "random", "sticky", "least_used"] = Field(
        "round_robin"
    )

    @field_validator("proxies")
    @classmethod
    def validate_proxies(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one proxy URL is required")
        return v


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class ConfigureRateLimitArgs(BaseModel):
    domain: Optional[str] = Field(None, description="Domain to configure; applies globally when omitted")
    requests_per_second: float = Field(1.0, gt=0, description="Maximum requests per second")
    requests_per_minute: Optional[int] = Field(None, gt=0)
    requests_per_hour: Optional[int] = Field(None, gt=0)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class SaveSessionArgs(BaseModel):
    session_id: str = Field(..., description="Identifier for the session to save")
    url: Optional[str] = Field(None, description="Optional URL context for the session")


class LoadSessionArgs(BaseModel):
    session_id: str = Field(..., description="Identifier of the session to load")


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

class RecordSessionArgs(_URLMixin):
    pass


class StopRecordingArgs(BaseModel):
    recording_id: str = Field(..., description="ID of the active recording to stop")


class GetRecordingStatusArgs(BaseModel):
    recording_id: str = Field(..., description="ID of the recording")


class DeleteRecordingArgs(BaseModel):
    recording_id: str = Field(..., description="ID of the recording to delete")


class ExportRecordingArgs(BaseModel):
    recording_id: str = Field(..., description="ID of the recording to export")
    format: Literal["json", "har", "playwright_test"] = Field("json", description="Export format")


class GenerateCrawlerArgs(BaseModel):
    recording_id: str = Field(..., description="ID of the recording to convert")
    output_format: Literal["yaml", "python", "playwright"] = Field("yaml")


# ---------------------------------------------------------------------------
# CDP
# ---------------------------------------------------------------------------

class ExecuteCDPArgs(_URLMixin):
    method: str = Field(..., description="CDP command name (e.g. 'Network.enable')")
    params: Optional[Dict[str, Any]] = Field(None, description="Optional command parameters")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class ClearCacheArgs(BaseModel):
    cache_type: Optional[Literal["page", "response", "state", "all"]] = Field(
        "all", description="Cache to clear; clears all when omitted"
    )


# ---------------------------------------------------------------------------
# Crawl / Structured Extraction
# ---------------------------------------------------------------------------

class CrawlArgs(_URLMixin, _DOMFilterMixin):
    max_depth: int = Field(2, ge=1, le=5, description="Maximum crawl depth (1 = seed page only)")
    max_pages: int = Field(10, ge=1, le=100, description="Maximum total pages to crawl")
    concurrency: int = Field(3, ge=1, le=10, description="Max concurrent page loads")
    ignore_external: bool = Field(True, description="Only crawl links within the same domain")
    save_to_file: bool = Field(False, description="Save crawling results to a file inside .crawls directory")


class StructuredExtractArgs(_URLMixin, _DOMFilterMixin):
    schema_def: Dict[str, Any] = Field(..., alias="schema", description="Target JSON schema structure for extraction")
    instructions: Optional[str] = Field(None, description="Optional natural-language guidance for extraction context")


# ---------------------------------------------------------------------------
# Xray / V2ray Proxy Management
# ---------------------------------------------------------------------------

class ConfigureXraySubscriptionArgs(BaseModel):
    subscription_url: Optional[str] = Field(None, description="URL containing base64 V2ray subscription configurations")
    raw_links: Optional[List[str]] = Field(None, description="List of raw protocol links (vmess://, vless://, trojan://, ss://)")
    num_ports: int = Field(3, ge=1, le=20, description="Number of concurrent SOCKS5 ports to run")
    start_port: int = Field(10801, ge=1024, le=65535, description="Starting port number for local SOCKS5 proxy inbounds")
    auto_benchmark: bool = Field(True, description="Automatically benchmark and sort nodes by speed on startup")
    test_url: str = Field("http://httpbin.org/ip", description="URL to check latency against during startup benchmark")


class GetXrayStatusArgs(BaseModel):
    pass


class RotateXrayNodeArgs(BaseModel):
    port: int = Field(..., ge=1024, le=65535, description="SOCKS5 port to rotate node on")


class TestXrayNodesArgs(BaseModel):
    test_url: str = Field("http://httpbin.org/ip", description="URL to check latency and connectivity against")
    max_concurrency: int = Field(5, ge=1, le=10, description="Max concurrent benchmark processes to spawn")
