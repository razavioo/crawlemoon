"""Utility functions for MCP server.

Provides:
- URL and argument validation helpers
- ``with_timeout`` / ``with_retry`` async decorators
- ``log_context`` — structured logging context manager that injects fields
  (tool_name, request_id, duration) into log records via a thread-local filter.
"""

import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, AsyncIterator, Dict, Optional, Tuple
from urllib.parse import urlparse

from ..exceptions import URLValidationError, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_SAFE_SCHEMES = {"http", "https"}
_URL_REGEX = re.compile(
    r"^(?:http|https)://"            # scheme
    r"(?:[A-Za-z0-9\-._~!$&'()*+,;=%]+@)?"  # optional userinfo
    r"(?:[A-Za-z0-9\-._~!$&'()*+,;=]|\[[\w:.]+\])+"  # host
    r"(?::\d+)?"                     # optional port
    r"(?:/[^\s]*)?"                  # optional path
    r"$",
    re.IGNORECASE,
)


def validate_url(url: str) -> bool:
    """Return ``True`` if *url* is a valid HTTP/HTTPS URL, ``False`` otherwise."""
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in _SAFE_SCHEMES and bool(parsed.netloc)
    except Exception:
        return False


def require_url(url: str, field: str = "url") -> None:
    """Raise :class:`~exceptions.URLValidationError` if *url* is not valid.

    Args:
        url: The URL to check.
        field: Name of the argument (used in the error message).

    Raises:
        URLValidationError: When the URL is invalid.
    """
    if not validate_url(url):
        raise URLValidationError(f"Invalid URL for argument '{field}': {url!r}")


def validate_arguments(
    arguments: Dict[str, Any],
    required: list,
    schema: Optional[Dict] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate tool arguments.

    Args:
        arguments: Arguments to validate.
        required: List of required argument names.
        schema: Unused (kept for backwards compatibility).

    Returns:
        Tuple of ``(is_valid, error_message)``.
    """
    for field in required:
        if field not in arguments:
            return False, f"Missing required argument: {field}"
        if arguments[field] is None:
            return False, f"Required argument '{field}' cannot be None"

    for field in ("url", "endpoint"):
        if field in arguments:
            url = arguments[field]
            if not isinstance(url, str):
                return False, f"'{field}' must be a string"
            if not validate_url(url):
                return False, f"Invalid URL format: {url}"

    return True, None


# ---------------------------------------------------------------------------
# Structured logging context
# ---------------------------------------------------------------------------

class _ContextFilter(logging.Filter):
    """Injects extra fields into log records while the context is active."""

    def __init__(self, extra: Dict[str, Any]):
        super().__init__()
        self._extra = extra

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        for key, value in self._extra.items():
            setattr(record, key, value)
        return True


@asynccontextmanager
async def log_context(
    tool_name: str,
    request_id: Optional[str] = None,
    **extra: Any,
) -> AsyncIterator[str]:
    """Async context manager that attaches structured fields to all log records.

    Usage::

        async with log_context("deep_analyze", url=url) as req_id:
            ...

    Args:
        tool_name: Name of the MCP tool being executed.
        request_id: Optional correlation ID; auto-generated when omitted.
        **extra: Additional key/value pairs to attach to log records.

    Yields:
        The request ID string.
    """
    req_id = request_id or str(uuid.uuid4())[:8]
    start = time.monotonic()
    ctx = {"tool_name": tool_name, "request_id": req_id, **extra}
    log_filter = _ContextFilter(ctx)

    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(log_filter)

    logger.info("Tool started: %s (req=%s)", tool_name, req_id)
    try:
        yield req_id
    finally:
        elapsed = time.monotonic() - start
        logger.info(
            "Tool finished: %s (req=%s, duration=%.3fs)",
            tool_name,
            req_id,
            elapsed,
        )
        for handler in root.handlers:
            handler.removeFilter(log_filter)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def with_timeout(timeout: float):
    """Decorator to add a timeout to an async function.

    Args:
        timeout: Timeout in seconds.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error("Function %s timed out after %.1fs", func.__name__, timeout)
                raise TimeoutError(f"Operation timed out after {timeout} seconds")
        return wrapper
    return decorator


def with_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,),
    backoff_factor: float = 1.0,
):
    """Decorator to add retry logic to an async function.

    Args:
        max_retries: Maximum number of retry attempts.
        delay: Initial delay between retries in seconds.
        exceptions: Tuple of exception types to catch and retry.
        backoff_factor: Multiplier applied to *delay* on each retry (1.0 = no backoff).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries - 1:
                        logger.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %.1fs…",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            exc,
                            current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            "All %d attempts failed for %s",
                            max_retries,
                            func.__name__,
                        )
            raise last_exception
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# JS payload validation (execute_js / execute_cdp / deobfuscate_js)
# ---------------------------------------------------------------------------

# Patterns disallowed in scripts handed to a real browser. The intent is not
# perfect sandboxing (impossible without a JS parser) but raising the bar above
# "anyone-with-MCP-access can pivot to RCE-shaped behavior".
_JS_DENYLIST = (
    re.compile(r"\beval\s*\("),
    re.compile(r"\bnew\s+Function\b"),
    re.compile(r"\bdocument\.write\b"),
    re.compile(r"\bimportScripts\s*\("),
    # Dynamic import() — distinct from static `import x from ...` parsing
    re.compile(r"(?<![A-Za-z0-9_$])import\s*\("),
    re.compile(r"\bWebAssembly\.(?:compile|instantiate)\b"),
)


def validate_js_payload(
    code: str,
    *,
    field: str = "script",
    max_length: int = 50_000,
    allow_dangerous: bool = False,
) -> None:
    """Validate a JavaScript payload before sending it to a browser context.

    Raises :class:`ValidationError` on failure. When *allow_dangerous* is
    ``False``, this is a hard refusal regardless of payload content — callers
    must explicitly opt in (typically via ``CRAWILFY_ALLOW_DANGEROUS_JS``).
    """
    if not isinstance(code, str) or not code.strip():
        raise ValidationError(f"'{field}' must be a non-empty string")
    if len(code) > max_length:
        raise ValidationError(
            f"'{field}' length {len(code)} exceeds limit {max_length}"
        )
    if not allow_dangerous:
        raise ValidationError(
            "JS execution is disabled. Set CRAWILFY_ALLOW_DANGEROUS_JS=true to "
            "enable execute_js / execute_cdp / deobfuscate_js."
        )
    for pattern in _JS_DENYLIST:
        if pattern.search(code):
            raise ValidationError(
                f"'{field}' contains disallowed construct: {pattern.pattern}"
            )


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def safe_get(dictionary: Dict, *keys, default: Any = None) -> Any:
    """Safely traverse nested dictionaries.

    Args:
        dictionary: Dictionary to search.
        *keys: Keys to traverse in order.
        default: Value returned when a key is missing.

    Returns:
        The value at the given path, or *default*.
    """
    result = dictionary
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    return result
