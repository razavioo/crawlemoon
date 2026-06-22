"""Proxy Pool Manager with rotation strategies and health checking."""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
from urllib.parse import quote, unquote, urlparse

import httpx


logger = logging.getLogger(__name__)


class ProxyType(Enum):
    """Proxy type."""
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class RotationStrategy(Enum):
    """Proxy rotation strategy."""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    STICKY = "sticky"  # Same proxy for same domain
    LEAST_USED = "least_used"


def _detect_proxy_type(scheme: str) -> ProxyType:
    """Resolve a URL scheme to a supported proxy type."""
    normalized = scheme.lower()
    if normalized == "https":
        return ProxyType.HTTPS
    if normalized == "socks4":
        return ProxyType.SOCKS4
    if normalized == "socks5":
        return ProxyType.SOCKS5
    return ProxyType.HTTP


def _split_proxy_lines(value: str) -> List[str]:
    """Split comma/newline separated proxy text while ignoring comments."""
    entries = []
    for line in value.replace(",", "\n").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            entries.append(cleaned)
    return entries


def load_proxy_entries_from_file(file_path: str) -> List[str]:
    """Load proxy entries from a local text file."""
    with open(file_path, "r", encoding="utf-8") as proxy_file:
        return _split_proxy_lines(proxy_file.read())


def parse_proxy_source(
    proxies: Optional[List[str]] = None,
    proxies_text: Optional[str] = None,
    proxies_file: Optional[str] = None,
) -> List[str]:
    """Collect proxy entries from list, text, and optional file sources."""
    entries: List[str] = []
    for proxy in proxies or []:
        entries.extend(_split_proxy_lines(proxy))
    if proxies_text:
        entries.extend(_split_proxy_lines(proxies_text))
    if proxies_file:
        entries.extend(load_proxy_entries_from_file(proxies_file))
    return entries


@dataclass
class Proxy:
    """Proxy configuration."""
    
    url: str
    proxy_type: ProxyType
    username: Optional[str] = None
    password: Optional[str] = None
    last_checked: Optional[datetime] = None
    is_healthy: bool = True
    failure_count: int = 0
    success_count: int = 0
    last_used: Optional[datetime] = None
    usage_count: int = 0
    is_xray: bool = False
    xray_port: Optional[int] = None
    source: str = "manual"
    metadata: Optional[Dict[str, Any]] = None
    
    def to_playwright_config(self) -> Dict[str, Any]:
        """Convert to Playwright proxy configuration."""
        parsed = urlparse(self.url)
        
        config = {
            "server": f"{parsed.scheme}://{parsed.netloc}",
        }
        
        if self.username and self.password:
            config["username"] = self.username
            config["password"] = self.password
        
        return config

    def to_httpx_proxy_url(self) -> str:
        """Convert to an httpx-compatible proxy URL."""
        if not self.username or not self.password:
            return self.url

        parsed = urlparse(self.url)
        username = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return f"{parsed.scheme}://{username}:{password}@{parsed.netloc}"

    def to_curl_cffi_proxies(self) -> Dict[str, str]:
        """Convert to curl_cffi requests proxy mapping."""
        proxy_url = self.to_httpx_proxy_url()
        return {"http": proxy_url, "https": proxy_url}

    def masked_url(self) -> str:
        """Return a log-safe proxy URL with credentials redacted."""
        parsed = urlparse(self.url)
        if not self.username and not self.password:
            return self.url
        username = quote(self.username or "", safe="")
        credential = f"{username}:***@" if username else "***@"
        return f"{parsed.scheme}://{credential}{parsed.netloc}"
    
    def mark_success(self):
        """Mark proxy as successful."""
        self.success_count += 1
        self.failure_count = 0
        self.is_healthy = True
        self.last_checked = datetime.now()
        self.last_used = datetime.now()
        self.usage_count += 1
    
    def mark_failure(self):
        """Mark proxy as failed."""
        self.failure_count += 1
        self.last_checked = datetime.now()
        
        # Mark unhealthy after 3 consecutive failures
        if self.failure_count >= 3:
            self.is_healthy = False
            logger.warning(f"Proxy {self.url} marked as unhealthy after {self.failure_count} failures")



class ProxyPool:
    """Manages a pool of proxies with rotation and health checking."""
    
    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        rotation_strategy: RotationStrategy = RotationStrategy.ROUND_ROBIN,
        health_check_interval: int = 300,  # 5 minutes
        health_check_timeout: float = 5.0,
        xray_manager: Optional[Any] = None,
        fail_closed: bool = False,
    ):
        self.proxies: List[Proxy] = []
        self.rotation_strategy = rotation_strategy
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        self.xray_manager = xray_manager
        self.fail_closed = fail_closed
        self._current_index = 0
        self._domain_proxy_map: Dict[str, Proxy] = {}  # For sticky strategy
        self._lock = asyncio.Lock()
        
        if proxies:
            self.add_proxies(proxies)
            
    def add_xray_proxy(self, port: int) -> Proxy:
        """Add a dynamic local Xray proxy to the pool."""
        proxy_url = f"socks5://127.0.0.1:{port}"
        proxy = Proxy(
            url=proxy_url,
            proxy_type=ProxyType.SOCKS5,
            is_xray=True,
            xray_port=port,
            source="xray",
            metadata={"port": port},
        )
        self.proxies.append(proxy)
        logger.info(f"Registered dynamic Xray proxy: {proxy_url} on port {port}")
        return proxy

    
    def add_proxies(self, proxy_urls: List[str]) -> None:
        """Add proxies to the pool."""
        for proxy_url in proxy_urls:
            self.add_proxy(proxy_url)
    
    @staticmethod
    def normalize_proxy(
        proxy_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        default_scheme: str = "http",
    ) -> Proxy:
        """Normalize URL and Webshare-style proxy entries into a Proxy object."""
        raw_proxy = proxy_url.strip()
        if not raw_proxy:
            raise ValueError("Proxy URL cannot be empty")

        default_scheme = (default_scheme or "http").lower()
        if default_scheme not in {"http", "https", "socks4", "socks5"}:
            raise ValueError("default_scheme must be one of: http, https, socks4, socks5")

        parsed = urlparse(raw_proxy)
        if parsed.scheme and parsed.scheme.lower() in {"http", "https", "socks4", "socks5"}:
            proxy_type = _detect_proxy_type(parsed.scheme)
            host = parsed.hostname
            port = parsed.port
            proxy_username = username if username is not None else unquote(parsed.username or "") or None
            proxy_password = password if password is not None else unquote(parsed.password or "") or None
            if not host or not port:
                raise ValueError(f"Invalid proxy URL: {proxy_url}")
            normalized_url = f"{parsed.scheme.lower()}://{host}:{port}"
            return Proxy(
                url=normalized_url,
                proxy_type=proxy_type,
                username=proxy_username,
                password=proxy_password,
            )

        parts = raw_proxy.split(":")
        if len(parts) not in {2, 4}:
            raise ValueError(
                "Proxy must be URL, host:port, or host:port:username:password"
            )

        host, port = parts[0].strip(), parts[1].strip()
        if not host or not port.isdigit():
            raise ValueError(f"Invalid proxy host/port: {proxy_url}")

        proxy_username = username
        proxy_password = password
        if len(parts) == 4:
            proxy_username = username if username is not None else parts[2].strip() or None
            proxy_password = password if password is not None else parts[3].strip() or None

        return Proxy(
            url=f"{default_scheme}://{host}:{port}",
            proxy_type=_detect_proxy_type(default_scheme),
            username=proxy_username,
            password=proxy_password,
        )

    def add_proxy(
        self,
        proxy_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        default_scheme: str = "http",
    ) -> Proxy:
        """Add a single proxy to the pool."""
        proxy = self.normalize_proxy(proxy_url, username, password, default_scheme)

        if any(
            existing.url == proxy.url
            and existing.username == proxy.username
            and existing.password == proxy.password
            for existing in self.proxies
        ):
            logger.debug("Skipping duplicate proxy: %s", proxy.masked_url())
            return proxy
        
        self.proxies.append(proxy)
        logger.info("Added proxy: %s", proxy.masked_url())
        
        return proxy
    
    def remove_proxy(self, proxy_url: str) -> bool:
        """Remove a proxy from the pool."""
        proxy = next((p for p in self.proxies if p.url == proxy_url), None)
        if proxy:
            self.proxies.remove(proxy)
            # Remove from sticky mapping if present
            self._domain_proxy_map = {
                domain: p for domain, p in self._domain_proxy_map.items()
                if p.url != proxy_url
            }
            logger.info(f"Removed proxy: {proxy_url}")
            return True
        return False
    
    async def get_proxy(self, domain: Optional[str] = None) -> Optional[Proxy]:
        """Get a proxy based on rotation strategy.

        Raises:
            NoHealthyProxyError: If a proxy pool is configured but all proxies
                are unhealthy *and* there are no proxies at all.
        """
        async with self._lock:
            if self.fail_closed and not self.proxies:
                from src.exceptions import NoHealthyProxyError
                raise NoHealthyProxyError("No proxies configured in the pool (fail-closed is enabled)")

            healthy_proxies = [p for p in self.proxies if p.is_healthy]

            if not healthy_proxies:
                if self.fail_closed:
                    from src.exceptions import NoHealthyProxyError
                    raise NoHealthyProxyError("All configured proxies are unhealthy (fail-closed is enabled)")
                logger.warning("No healthy proxies available, falling back to all proxies")
                # Fallback to unhealthy proxies rather than blocking the caller
                healthy_proxies = self.proxies

            if not healthy_proxies:
                return None
            
            # Sticky strategy: use same proxy for same domain
            if self.rotation_strategy == RotationStrategy.STICKY and domain:
                if domain in self._domain_proxy_map:
                    proxy = self._domain_proxy_map[domain]
                    if proxy in healthy_proxies:
                        return proxy
                # Assign new proxy for domain
                proxy = self._select_proxy(healthy_proxies)
                self._domain_proxy_map[domain] = proxy
                return proxy
            
            return self._select_proxy(healthy_proxies)
    
    def _select_proxy(self, proxies: List[Proxy]) -> Proxy:
        """Select proxy based on rotation strategy."""
        if not proxies:
            return None
        
        if self.rotation_strategy == RotationStrategy.ROUND_ROBIN:
            proxy = proxies[self._current_index % len(proxies)]
            self._current_index += 1
            return proxy
        
        elif self.rotation_strategy == RotationStrategy.RANDOM:
            return random.choice(proxies)
        
        elif self.rotation_strategy == RotationStrategy.LEAST_USED:
            return min(proxies, key=lambda p: p.usage_count)
        
        else:
            # Default to round robin
            proxy = proxies[self._current_index % len(proxies)]
            self._current_index += 1
            return proxy
    
    async def health_check(self, proxy: Proxy, test_url: str = "http://httpbin.org/ip") -> bool:
        """Check if a proxy is healthy."""
        try:
            proxy_config = proxy.to_playwright_config()
            
            # For health check, we'll use httpx with proxy
            proxy_url = proxy.url
            if proxy.username and proxy.password:
                proxy_url = proxy.to_httpx_proxy_url()
            
            async with httpx.AsyncClient(
                proxies={proxy_config["server"]: proxy_url},
                timeout=self.health_check_timeout,
            ) as client:
                response = await client.get(test_url)
                if response.status_code == 200:
                    proxy.mark_success()
                    return True
                else:
                    if proxy.is_xray and self.xray_manager and proxy.xray_port:
                        logger.warning(f"Xray Proxy on port {proxy.xray_port} failed health check. Rotating node...")
                        try:
                            self.xray_manager.rotate_node(proxy.xray_port)
                            proxy.mark_success()  # Re-enable after rotation
                            return True
                        except Exception as rotate_err:
                            logger.error(f"Failed to auto-rotate Xray proxy on port {proxy.xray_port}: {rotate_err}")
                    proxy.mark_failure()
                    return False
        
        except (httpx.RequestError, httpx.HTTPStatusError, OSError) as exc:
            logger.debug("Health check failed for %s: %s", proxy.url, exc)
            if proxy.is_xray and self.xray_manager and proxy.xray_port:
                logger.warning(f"Xray Proxy on port {proxy.xray_port} failed health check: {exc}. Rotating node...")
                try:
                    self.xray_manager.rotate_node(proxy.xray_port)
                    proxy.mark_success()  # Re-enable after rotation
                    return True
                except Exception as rotate_err:
                    logger.error(f"Failed to auto-rotate Xray proxy on port {proxy.xray_port}: {rotate_err}")
            proxy.mark_failure()
            return False
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all proxies."""
        results = {}
        
        tasks = [self.health_check(proxy) for proxy in self.proxies]
        health_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for proxy, result in zip(self.proxies, health_results):
            if isinstance(result, Exception):
                proxy.mark_failure()
                results[proxy.url] = False
            else:
                results[proxy.url] = result
        
        return results
    
    async def start_health_check_loop(self) -> None:
        """Start background health checking."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self.health_check_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in proxy health-check loop: %s", exc, exc_info=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get proxy pool statistics."""
        healthy = [p for p in self.proxies if p.is_healthy]
        unhealthy = [p for p in self.proxies if not p.is_healthy]
        
        return {
            "total": len(self.proxies),
            "healthy": len(healthy),
            "unhealthy": len(unhealthy),
            "rotation_strategy": self.rotation_strategy.value,
            "proxies": [
                {
                    "url": p.masked_url(),
                    "type": p.proxy_type.value,
                    "healthy": p.is_healthy,
                    "usage_count": p.usage_count,
                    "success_count": p.success_count,
                    "failure_count": p.failure_count,
                }
                for p in self.proxies
            ],
        }
