"""Stealth HTTP client with TLS fingerprint impersonation using curl_cffi."""

import logging
from typing import Optional, Dict, Any
from curl_cffi import requests
from fake_useragent import UserAgent

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


class StealthHTTPClient:
    """HTTP client with TLS fingerprint impersonation for bypassing bot detection."""
    
    def __init__(
        self,
        browser_profile: str = "chrome120",
        timeout: int = 30,
        verify: bool = True,
        proxies: Optional[Dict[str, str]] = None,
    ):
        """Initialize stealth HTTP client.
        
        Args:
            browser_profile: Browser profile to impersonate (chrome120, edge120, etc.)
            timeout: Request timeout in seconds
            verify: Verify SSL certificates
            proxies: Optional proxy configuration
        """
        self.browser_profile = browser_profile
        self.timeout = timeout
        self.verify = verify
        self.proxies = proxies
        self.ua = UserAgent()
        
        # Validate browser profile
        if browser_profile not in BROWSER_PROFILES.values():
            logger.warning(f"Unknown browser profile: {browser_profile}, using chrome120")
            self.browser_profile = "chrome120"
    
    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> requests.Response:
        """Make a GET request with TLS fingerprint impersonation.
        
        Args:
            url: Target URL
            headers: Optional custom headers
            params: Optional query parameters
            **kwargs: Additional arguments passed to requests.get
            
        Returns:
            Response object
        """
        headers = headers or {}
        
        # Use fake-useragent for realistic user agent
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.ua.random
        
        # Set realistic headers
        headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        headers.setdefault("Accept-Encoding", "gzip, deflate, br")
        headers.setdefault("DNT", "1")
        headers.setdefault("Connection", "keep-alive")
        headers.setdefault("Upgrade-Insecure-Requests", "1")
        headers.setdefault("Sec-Fetch-Dest", "document")
        headers.setdefault("Sec-Fetch-Mode", "navigate")
        headers.setdefault("Sec-Fetch-Site", "none")
        headers.setdefault("Sec-Fetch-User", "?1")
        
        return requests.get(
            url,
            headers=headers,
            params=params,
            impersonate=self.browser_profile,
            timeout=self.timeout,
            verify=self.verify,
            proxies=self.proxies,
            **kwargs
        )
    
    def post(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> requests.Response:
        """Make a POST request with TLS fingerprint impersonation.
        
        Args:
            url: Target URL
            data: Optional form data
            json: Optional JSON data
            headers: Optional custom headers
            **kwargs: Additional arguments passed to requests.post
            
        Returns:
            Response object
        """
        headers = headers or {}
        
        # Use fake-useragent for realistic user agent
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.ua.random
        
        # Set realistic headers for POST
        headers.setdefault("Accept", "application/json, text/plain, */*")
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        headers.setdefault("Content-Type", "application/json" if json else "application/x-www-form-urlencoded")
        headers.setdefault("Origin", url.split("/")[0] + "//" + url.split("/")[2])
        headers.setdefault("Referer", url)
        headers.setdefault("Sec-Fetch-Dest", "empty")
        headers.setdefault("Sec-Fetch-Mode", "cors")
        headers.setdefault("Sec-Fetch-Site", "same-origin")
        
        return requests.post(
            url,
            data=data,
            json=json,
            headers=headers,
            impersonate=self.browser_profile,
            timeout=self.timeout,
            verify=self.verify,
            proxies=self.proxies,
            **kwargs
        )
    
    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> requests.Response:
        """Make a custom request with TLS fingerprint impersonation.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            headers: Optional custom headers
            **kwargs: Additional arguments passed to requests.request
            
        Returns:
            Response object
        """
        headers = headers or {}
        
        # Use fake-useragent for realistic user agent
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.ua.random
        
        return requests.request(
            method,
            url,
            headers=headers,
            impersonate=self.browser_profile,
            timeout=self.timeout,
            verify=self.verify,
            proxies=self.proxies,
            **kwargs
        )


def create_stealth_client(
    browser: str = "chrome",
    version: Optional[str] = None,
    proxies: Optional[Dict[str, str]] = None,
) -> StealthHTTPClient:
    """Create a stealth HTTP client with specified browser profile.
    
    Args:
        browser: Browser type (chrome, edge, safari, firefox)
        version: Browser version (optional, uses latest if not specified)
        proxies: Optional proxy configuration
        
    Returns:
        StealthHTTPClient instance
    """
    if browser == "chrome":
        profile = f"chrome{version}" if version else "chrome120"
    elif browser == "edge":
        profile = f"edge{version}" if version else "edge120"
    elif browser == "safari":
        profile = f"safari{version}" if version else "safari17_0"
    elif browser == "firefox":
        profile = f"ff{version}" if version else "ff120"
    else:
        profile = "chrome120"
    
    if profile not in BROWSER_PROFILES.values():
        profile = "chrome120"
    
    return StealthHTTPClient(browser_profile=profile, proxies=proxies)

