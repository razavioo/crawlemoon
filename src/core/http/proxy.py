"""Shared proxy helpers for HTTP clients."""

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ..browser.proxy_pool import Proxy, ProxyPool


_proxy_pool: Optional[ProxyPool] = None


def set_http_proxy_pool(proxy_pool: Optional[ProxyPool]) -> None:
    """Register the process-wide proxy pool for internal HTTP clients."""
    global _proxy_pool
    _proxy_pool = proxy_pool


def get_http_proxy_pool() -> Optional[ProxyPool]:
    """Return the process-wide proxy pool, if configured."""
    return _proxy_pool


async def select_proxy_for_url(url: str) -> Optional[Proxy]:
    """Select a proxy for a URL using the active pool and domain-aware routing."""
    if not _proxy_pool:
        return None
    return await _proxy_pool.get_proxy(domain=urlparse(url).netloc)


async def httpx_proxy_kwargs(url: str) -> Dict[str, Any]:
    """Build httpx AsyncClient kwargs for the active proxy pool."""
    proxy = await select_proxy_for_url(url)
    if not proxy:
        return {}
    proxy_url = proxy.to_httpx_proxy_url()
    return {"proxies": {"http://": proxy_url, "https://": proxy_url}}


async def curl_cffi_proxy_config(url: str) -> tuple[Optional[Proxy], Optional[Dict[str, str]]]:
    """Build curl_cffi proxy mapping for the active proxy pool."""
    proxy = await select_proxy_for_url(url)
    if not proxy:
        return None, None
    return proxy, proxy.to_curl_cffi_proxies()
