"""Stealth HTTP client with TLS fingerprint impersonation using curl_cffi.

Connection pooling is handled transparently by curl_cffi's ``Session`` object,
which keeps persistent connections alive across requests.
"""

import logging
from typing import Optional, Dict, Any

from curl_cffi import requests as cffi_requests
from fake_useragent import UserAgent

from ...exceptions import HTTPRequestError

logger = logging.getLogger(__name__)

# Browser impersonation profiles
BROWSER_PROFILES = {
    "chrome": "chrome120",
    "chrome110": "chrome110",
    "chrome107": "chrome107",
    "chrome104": "chrome104",
    "chrome99": "chrome99",
    "edge": "edge120",
    "edge99": "edge99",
    "safari": "safari17_0",
    "safari15_6": "safari15_6",
    "safari15_5": "safari15_5",
    "firefox": "ff120",
    "ff109": "ff109",
    "ff104": "ff104",
}

_DEFAULT_GET_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

_DEFAULT_POST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class StealthHTTPClient:
    """HTTP client with TLS fingerprint impersonation and connection pooling.

    Uses ``curl_cffi.requests.Session`` to maintain a persistent connection pool,
    reducing handshake overhead for repeated requests to the same host.

    Args:
        browser_profile: Browser profile to impersonate (e.g. ``chrome120``).
        timeout: Request timeout in seconds.
        verify: Whether to verify SSL certificates.
        proxies: Optional proxy configuration dict (``{"https": "http://..."}``).
    """

    def __init__(
        self,
        browser_profile: str = "chrome120",
        timeout: int = 30,
        verify: bool = True,
        proxies: Optional[Dict[str, str]] = None,
    ):
        if browser_profile not in BROWSER_PROFILES.values():
            logger.warning(
                "Unknown browser profile %r — falling back to chrome120", browser_profile
            )
            browser_profile = "chrome120"

        self.browser_profile = browser_profile
        self.timeout = timeout
        self.verify = verify
        self.proxies = proxies
        self.ua = UserAgent()

        # Persistent session for connection pooling
        self._session = cffi_requests.Session(impersonate=self.browser_profile)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _base_headers(self) -> Dict[str, str]:
        return {"User-Agent": self.ua.random}

    def _common_kwargs(self) -> Dict[str, Any]:
        return {
            "timeout": self.timeout,
            "verify": self.verify,
            "proxies": self.proxies,
        }

    # ------------------------------------------------------------------
    # Public request methods
    # ------------------------------------------------------------------

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> cffi_requests.Response:
        """Make a GET request with TLS fingerprint impersonation.

        Args:
            url: Target URL.
            headers: Optional custom headers (merged with realistic defaults).
            params: Optional query parameters.
            **kwargs: Forwarded to the underlying session request.

        Returns:
            Response object.

        Raises:
            HTTPRequestError: On network or protocol failure.
        """
        merged = {**_DEFAULT_GET_HEADERS, **self._base_headers(), **(headers or {})}
        try:
            return self._session.get(
                url,
                headers=merged,
                params=params,
                **self._common_kwargs(),
                **kwargs,
            )
        except Exception as exc:
            raise HTTPRequestError(f"GET {url} failed: {exc}") from exc

    def post(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> cffi_requests.Response:
        """Make a POST request with TLS fingerprint impersonation.

        Args:
            url: Target URL.
            data: Optional form data.
            json: Optional JSON payload.
            headers: Optional custom headers.
            **kwargs: Forwarded to the underlying session request.

        Returns:
            Response object.

        Raises:
            HTTPRequestError: On network or protocol failure.
        """
        content_type = "application/json" if json is not None else "application/x-www-form-urlencoded"
        merged = {
            **_DEFAULT_POST_HEADERS,
            **self._base_headers(),
            "Content-Type": content_type,
            **(headers or {}),
        }
        try:
            return self._session.post(
                url,
                data=data,
                json=json,
                headers=merged,
                **self._common_kwargs(),
                **kwargs,
            )
        except Exception as exc:
            raise HTTPRequestError(f"POST {url} failed: {exc}") from exc

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> cffi_requests.Response:
        """Make an arbitrary HTTP request with TLS fingerprint impersonation.

        Args:
            method: HTTP method string (``GET``, ``POST``, etc.).
            url: Target URL.
            headers: Optional custom headers.
            **kwargs: Forwarded to the underlying session request.

        Returns:
            Response object.

        Raises:
            HTTPRequestError: On network or protocol failure.
        """
        merged = {**self._base_headers(), **(headers or {})}
        try:
            return self._session.request(
                method,
                url,
                headers=merged,
                **self._common_kwargs(),
                **kwargs,
            )
        except Exception as exc:
            raise HTTPRequestError(f"{method} {url} failed: {exc}") from exc

    def close(self) -> None:
        """Close the underlying connection pool."""
        try:
            self._session.close()
        except Exception as exc:
            logger.debug("Error closing stealth HTTP session: %s", exc)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_stealth_client(
    browser: str = "chrome",
    version: Optional[str] = None,
    proxies: Optional[Dict[str, str]] = None,
) -> StealthHTTPClient:
    """Create a stealth HTTP client for the given browser profile.

    Args:
        browser: Browser type (``chrome``, ``edge``, ``safari``, ``firefox``).
        version: Optional version suffix.  Uses latest when omitted.
        proxies: Optional proxy configuration.

    Returns:
        A configured :class:`StealthHTTPClient` instance.
    """
    profile_map = {
        "chrome": f"chrome{version}" if version else "chrome120",
        "edge": f"edge{version}" if version else "edge120",
        "safari": f"safari{version}" if version else "safari17_0",
        "firefox": f"ff{version}" if version else "ff120",
    }
    profile = profile_map.get(browser, "chrome120")
    if profile not in BROWSER_PROFILES.values():
        profile = "chrome120"
    return StealthHTTPClient(browser_profile=profile, proxies=proxies)
