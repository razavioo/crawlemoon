"""Structured logging utilities for Crawilfy MCP Server.

Features:
- ``SensitiveDataFilter`` — strips API keys, passwords, and credentialed URLs
  from log records before they are emitted.
- ``setup_logging`` — configure the root logger once at startup with the
  filter applied to every handler.
"""

import logging
import re
import os
from typing import Optional

# ---------------------------------------------------------------------------
# Patterns that should never appear in log output
# ---------------------------------------------------------------------------

_REDACT_PATTERNS = [
    # Bearer / API-key style tokens (≥20 chars of base64url or hex chars)
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-_=]{20,}", re.IGNORECASE),
    # Authorization header values
    re.compile(r"(Authorization:\s*\S+\s+)[A-Za-z0-9\-_=]{20,}", re.IGNORECASE),
    # URLs with embedded credentials: scheme://user:password@host
    re.compile(r"(\w+://[^:@/ ]+:)[^@/ ]+(@)", re.IGNORECASE),
    # Generic key=value patterns that look like secrets
    re.compile(
        r"((?:api[_-]?key|secret|password|passwd|token|access[_-]?key)"
        r"\s*[=:]\s*)['\"]?[A-Za-z0-9\-_]{8,}['\"]?",
        re.IGNORECASE,
    ),
    # OpenAI / Anthropic / common SDK key formats
    re.compile(r"(sk-|sk-ant-|gsk_|xai-)[A-Za-z0-9\-_]{20,}"),
]

_REDACTED = "[REDACTED]"


def _scrub(text: str) -> str:
    """Replace sensitive substrings in *text* with ``[REDACTED]``."""
    for pattern in _REDACT_PATTERNS:
        # Keep the non-secret group (group 1) and replace the rest
        def _replace(m: re.Match) -> str:
            groups = m.groups()
            if groups:
                # Replace everything after the first capture group
                prefix = groups[0]
                # If there's a trailing group (e.g. the '@' in credentials)
                suffix = groups[-1] if len(groups) > 1 else ""
                return f"{prefix}{_REDACTED}{suffix}"
            return _REDACTED

        text = pattern.sub(_replace, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts secrets from log messages and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # Scrub the message
        try:
            record.msg = _scrub(str(record.msg))
        except Exception:
            pass

        # Scrub formatted args (args are not yet interpolated here)
        if record.args:
            try:
                if isinstance(record.args, dict):
                    record.args = {
                        k: _scrub(str(v)) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        _scrub(str(a)) if isinstance(a, str) else a
                        for a in record.args
                    )
            except Exception:
                pass

        # Scrub exception text
        if record.exc_info and record.exc_info[1]:
            try:
                exc = record.exc_info[1]
                if exc.args:
                    exc.args = tuple(
                        _scrub(str(a)) if isinstance(a, str) else a
                        for a in exc.args
                    )
            except Exception:
                pass

        return True


def setup_logging(
    level: Optional[str] = None,
    fmt: str = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
) -> None:
    """Configure root logger with the sensitive-data filter applied.

    Args:
        level: Log level string (``DEBUG``, ``INFO``, …).  Defaults to the
            ``LOG_LEVEL`` env-var or ``INFO``.
        fmt: Log format string.
    """
    resolved_level = level or os.getenv("LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, resolved_level.upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid duplicate handlers if called multiple times
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    else:
        # Ensure the filter is on every existing handler
        for h in root.handlers:
            if not any(isinstance(f, SensitiveDataFilter) for f in h.filters):
                h.addFilter(SensitiveDataFilter())

    logger = logging.getLogger(__name__)
    logger.debug("Logging configured at level %s", resolved_level.upper())
