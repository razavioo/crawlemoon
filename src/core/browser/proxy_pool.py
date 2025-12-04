"""Proxy Pool Manager with rotation strategies and health checking."""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timedelta
from urllib.parse import urlparse

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
    ):
        self.proxies: List[Proxy] = []
        self.rotation_strategy = rotation_strategy
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        self._current_index = 0
        self._domain_proxy_map: Dict[str, Proxy] = {}  # For sticky strategy
        self._lock = asyncio.Lock()
        
        if proxies:
            self.add_proxies(proxies)
    
    def add_proxies(self, proxy_urls: List[str]) -> None:
        """Add proxies to the pool."""
        for proxy_url in proxy_urls:
            self.add_proxy(proxy_url)
    
    def add_proxy(self, proxy_url: str, username: Optional[str] = None, password: Optional[str] = None) -> Proxy:
        """Add a single proxy to the pool."""
        parsed = urlparse(proxy_url)
        
        # Determine proxy type from scheme
        scheme = parsed.scheme.lower()
        if scheme == "http":
            proxy_type = ProxyType.HTTP
        elif scheme == "https":
            proxy_type = ProxyType.HTTPS
        elif scheme == "socks4":
            proxy_type = ProxyType.SOCKS4
        elif scheme == "socks5":
            proxy_type = ProxyType.SOCKS5
        else:
            # Default to HTTP
            proxy_type = ProxyType.HTTP
            proxy_url = f"http://{proxy_url}" if "://" not in proxy_url else proxy_url
        
        proxy = Proxy(
            url=proxy_url,
            proxy_type=proxy_type,
            username=username,
            password=password,
        )
        
        self.proxies.append(proxy)
        logger.info(f"Added proxy: {proxy_url}")
        
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
        """Get a proxy based on rotation strategy."""
        async with self._lock:
            healthy_proxies = [p for p in self.proxies if p.is_healthy]
            
            if not healthy_proxies:
                logger.warning("No healthy proxies available")
                # Fallback to unhealthy proxies if none are healthy
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
    
    async def health_check(self, proxy: Proxy) -> bool:
        """Check if a proxy is healthy."""
        try:
            # Use a simple HTTP request to test proxy
            test_url = "http://httpbin.org/ip"
            
            proxy_config = proxy.to_playwright_config()
            
            # For health check, we'll use httpx with proxy
            proxy_url = proxy.url
            if proxy.username and proxy.password:
                parsed = urlparse(proxy_url)
                proxy_url = f"{parsed.scheme}://{proxy.username}:{proxy.password}@{parsed.netloc}"
            
            async with httpx.AsyncClient(
                proxies={proxy_config["server"]: proxy_url},
                timeout=self.health_check_timeout,
            ) as client:
                response = await client.get(test_url)
                if response.status_code == 200:
                    proxy.mark_success()
                    return True
                else:
                    proxy.mark_failure()
                    return False
        
        except Exception as e:
            logger.debug(f"Health check failed for {proxy.url}: {e}")
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
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
    
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
                    "url": p.url,
                    "type": p.proxy_type.value,
                    "healthy": p.is_healthy,
                    "usage_count": p.usage_count,
                    "success_count": p.success_count,
                    "failure_count": p.failure_count,
                }
                for p in self.proxies
            ],
        }

